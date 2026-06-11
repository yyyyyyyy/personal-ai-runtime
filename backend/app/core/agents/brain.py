"""Brain — the core reasoning loop: conversation → tool calls → response.

Brain is stateless. It takes context, calls the LLM, routes tool invocations,
and returns a response. It does NOT own state — that belongs to Runtime.
"""

import json
import time
import uuid
from typing import AsyncIterator

from app.config import settings
from app.core.agents.context_engine import context_engine
from app.core.agents.conversation import ConversationManager
from app.core.agents.llm_router import llm_router
from app.core.agents.memory_extractor import memory_extractor
from app.core.agents.tool_postprocess import (
    build_prompt_hints,
    canned_summary,
    compact_for_llm,
)
from app.core.runtime.conversation_recorder import record_conversation_turn
from app.core.runtime.egress.egress_gate import prepare_llm_egress
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.taint import is_external_ingestion_tool, taint_registry
from app.core.telemetry.telemetry import LLMCallRecord, telemetry

SYSTEM_PROMPT = """You are Personal AI Runtime — a personal AI assistant that helps users manage their life, work, and goals.

You are:
- Helpful: Provide clear, actionable responses.
- Honest: Admit when you don't know something. Never fabricate information.
- Proactive: When you see an opportunity to help with tools, use them.
- Concise: Get to the point. Users value brevity.

You have access to tools. Use them when they would help answer the user's query.
When using tools, briefly explain what you're doing before calling them.

Current context (if available) will include the user's active goals, recent events, and relevant memories.
Memories may appear in two sections:
- "你告诉过我的（你的自述）" — the user's own words; treat as authoritative about themselves.
- "系统推测（假设，非定论）" — system hypotheses with confidence scores; NOT facts about who the user is.
Never restate a system hypothesis as a definitive statement about the user (e.g. do not say "你是…" based on a hypothesis).
When self-report and system hypothesis conflict, defer to the user's self-report.
Use this context to provide personalized, relevant responses."""


class Brain:
    """Stateless reasoning engine. One instance per request. Uses LLM Router for multi-provider support."""

    def __init__(self):
        self.client, self.provider = llm_router.get_client()

    async def chat_stream(
        self, conversation: ConversationManager, user_message: str
    ) -> AsyncIterator[dict]:
        """Process a user message and stream the response.

        Supports multi-LLM fallback: if the primary provider fails, tries alternatives.
        """
        correlation_id = f"chat-{uuid.uuid4().hex[:16]}"
        taint_registry.clear(correlation_id)

        # Step 1: Build the messages array
        messages = self._build_messages(conversation, user_message)

        # Step 2: Save user message
        conversation.save_user_message(user_message)

        # Step 3: Run the LLM → tool call loop
        full_content = ""
        canned_response_done = False
        tool_iterations = 0
        loop_start = time.time()

        while tool_iterations < settings.max_tool_iterations:
            if time.time() - loop_start > settings.total_tool_loop_timeout:
                yield {"type": "error", "content": "Tool call loop timed out."}
                return

            # Call LLM (with multi-provider fallback)
            llm_start = time.time()
            try:
                response, client, used_provider = await self._create_llm_stream(messages)
            except Exception as e:
                yield {"type": "error", "content": f"LLM API error: {str(e)}"}
                return
            if used_provider.name != self.provider.name:
                self.client, self.provider = client, used_provider

            # Collect streaming response (gated at sentence boundaries)
            assistant_content = ""
            stream_gated = ""
            tool_calls_data: list[dict] = []
            current_tool_call: dict[str, int | str] = {
                "index": -1, "id": "", "function_name": "", "arguments": "",
            }

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text content
                if delta.content:
                    safe_delta = delta.content
                    if settings.meaning_gate_enabled:
                        from app.experimental.meaning_gate import gate_stream_delta

                        stream_gated, safe_delta, _gate_warnings = gate_stream_delta(
                            stream_gated, delta.content
                        )
                    else:
                        stream_gated += delta.content
                    assistant_content += safe_delta
                    yield {"type": "text_delta", "content": safe_delta}

                # Tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index is not None and tc.index != current_tool_call["index"]:
                            # New tool call
                            if int(current_tool_call["index"]) >= 0:
                                tool_calls_data.append(dict(current_tool_call))
                            current_tool_call = {
                                "index": tc.index,
                                "id": tc.id or "",
                                "function_name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            current_tool_call["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_call["function_name"] += tc.function.name
                            if tc.function.arguments:
                                current_tool_call["arguments"] += tc.function.arguments

            # Finalize last tool call
            if int(current_tool_call["index"]) >= 0:
                tool_calls_data.append(dict(current_tool_call))

            # Record LLM call
            llm_latency = (time.time() - llm_start) * 1000
            prompt_tokens = sum(len(msg.get("content") or "") // 4 for msg in messages)
            completion_tokens = len(assistant_content) // 4
            estimated_cost = (prompt_tokens * 0.000001 + completion_tokens * 0.000002)  # generic estimate
            telemetry.record_llm_call(LLMCallRecord(
                provider=self.provider.name,
                model=self.provider.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=llm_latency,
                cost=estimated_cost,
            ))

            # If LLM returned a text response without tool calls
            if not tool_calls_data:
                full_content = assistant_content
                if not full_content.strip():
                    full_content = await self._complete_text_only(messages, user_message)
                    if full_content:
                        yield {"type": "text_delta", "content": full_content}
                break

            # Process tool calls
            yield {"type": "tool_call_start", "tool_calls": tool_calls_data}

            # Add assistant message with tool calls to messages
            assistant_msg: dict = {"role": "assistant", "content": assistant_content or None}
            tc_for_msg = []
            for tc in tool_calls_data:
                tc_for_msg.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function_name"],
                        "arguments": tc["arguments"],
                    },
                })
            assistant_msg["tool_calls"] = tc_for_msg
            messages.append(assistant_msg)

            # Save assistant message with tool calls FIRST (so it appears before tool results in DB)
            conversation.save_assistant_message(
                assistant_content or "",
                tool_calls=tc_for_msg if tool_calls_data else None,
            )

            iteration_tool_results: list[dict] = []

            # Now save tool results
            for tc in tool_calls_data:
                tool_name = tc["function_name"]
                try:
                    tool_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    tool_args = {}

                # Invoke capability through Kernel (approval gating)
                cap_result = await kernel.invoke_capability(
                    name=tool_name,
                    args=tool_args,
                    actor="user",
                    correlation_id=correlation_id,
                )

                if is_external_ingestion_tool(tool_name):
                    taint_registry.mark(
                        correlation_id,
                        source="external_ingestion",
                        reason=tool_name,
                    )

                if cap_result["status"] == "pending":
                    yield {
                        "type": "confirmation_required",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_call_id": tc["id"],
                        "approval_id": cap_result["approval_id"],
                    }
                    # Suspend turn — resolve_approval will persist the sole tool result.
                    yield {"type": "done"}
                    return
                elif cap_result["status"] == "success":
                    tool_result = cap_result["result"]
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    }
                else:
                    tool_result = json.dumps({
                        "status": "error",
                        "error": cap_result.get("error", "unknown"),
                    })
                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    }

                iteration_tool_results.append({
                    "tool_name": tool_name,
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

                # Add tool result to messages (compact large payloads for LLM context)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": compact_for_llm(tool_name, tool_result),
                })

                # Persist tool result
                conversation.save_tool_result(tool_result, tc["id"])

            summary = canned_summary(tool_calls_data, iteration_tool_results)
            if summary:
                full_content = summary
                canned_response_done = True
                yield {"type": "text_delta", "content": full_content}
                break

            tool_iterations += 1
            if tool_iterations >= settings.max_tool_iterations:
                if assistant_content:
                    full_content = assistant_content
                    yield {"type": "text_delta", "content": assistant_content}
                else:
                    synthesized = await self._synthesize_from_tool_results(messages)
                    if synthesized:
                        full_content = synthesized
                        yield {"type": "text_delta", "content": synthesized}
                if full_content:
                    note = "\n\n（已达工具调用次数上限，以上为根据已收集信息生成的回复。）"
                    full_content += note
                    yield {"type": "text_delta", "content": note}
                else:
                    yield {
                        "type": "error",
                        "content": "达到了最大工具调用次数，且无法根据已有结果生成回复。",
                    }
                break

        # Step 4: Meaning gate + save + conversation episode
        if full_content and not canned_response_done:
            if settings.meaning_gate_enabled:
                from app.experimental.meaning_gate import gate_assistant_text

                full_content, _warnings = gate_assistant_text(full_content)
            conversation.save_assistant_message(full_content)

        record_conversation_turn(
            conversation.conversation_id,
            user_message,
            full_content or "",
        )

        # Fire-and-forget memory extraction (no-op when Ollama unavailable).
        memory_extractor.schedule(
            f"User: {user_message}\nAssistant: {full_content}",
            source=f"conv:{conversation.conversation_id}",
        )

        yield {"type": "done"}

    async def continue_after_tool_result(self, conversation: ConversationManager) -> str:
        """One-shot LLM completion after approval resolution closes the tool loop."""
        messages = self._build_messages(conversation, user_message="")
        # Drop the trailing empty user message added by _build_messages.
        if messages and messages[-1].get("role") == "user" and not messages[-1].get("content"):
            messages.pop()

        egress_messages, _egress_audit = prepare_llm_egress(
            messages, purpose="chat_continue"
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.provider.model,
                messages=egress_messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except Exception as e:
            err = f"无法生成后续回复: {e}"
            conversation.save_assistant_message(err)
            return err

        content = response.choices[0].message.content or ""
        if content:
            if settings.meaning_gate_enabled:
                from app.experimental.meaning_gate import gate_assistant_text

                content, _warnings = gate_assistant_text(content)
            conversation.save_assistant_message(content)
        return content

    async def _create_llm_stream(self, messages: list[dict]):
        """Try primary LLM provider, then fallbacks."""
        from openai import AsyncOpenAI

        from app.core.agents.llm_router import LLMProvider

        candidates: list[tuple[AsyncOpenAI, LLMProvider]] = [
            (self.client, self.provider),
            *llm_router.get_fallback_clients(),
        ]
        last_error: Exception | None = None
        llm_start = time.time()
        egress_messages, _egress_audit = prepare_llm_egress(messages, purpose="chat_stream")
        for client, provider in candidates:
            try:
                response = await client.chat.completions.create(  # type: ignore[call-overload]
                    model=provider.model,
                    messages=egress_messages,
                    tools=kernel.list_capability_definitions(),
                    tool_choice="auto",
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    stream=True,
                )
                telemetry.record_llm_call(LLMCallRecord(
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=(time.time() - llm_start) * 1000,
                    success=True,
                ))
                return response, client, provider
            except Exception as e:
                last_error = e
                telemetry.record_llm_call(LLMCallRecord(
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=(time.time() - llm_start) * 1000,
                    success=False,
                    error_message=str(e),
                ))
        raise last_error or RuntimeError("No LLM provider available")

    async def _synthesize_from_tool_results(self, messages: list[dict]) -> str:
        """Final text-only pass when the tool loop hits its iteration cap."""
        synth_messages = list(messages)
        synth_messages.append({
            "role": "user",
            "content": (
                "已达到工具调用次数上限。请仅根据上述对话与工具返回的结果，"
                "用中文直接回答用户最初的问题，不要再调用任何工具。"
            ),
        })
        try:
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.provider.model,
                messages=synth_messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            return ""

    async def _complete_text_only(self, messages: list[dict], user_message: str) -> str:
        """Retry once without tools when the model returns an empty completion."""
        retry_messages = list(messages)
        retry_messages.append({
            "role": "user",
            "content": (
                f"{user_message}\n\n"
                "(请直接文字回复。)"
            ),
        })
        try:
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.provider.model,
                messages=retry_messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            return "抱歉，我暂时无法生成回复，请再试一次。"

    def _build_messages(self, conversation: ConversationManager, user_message: str) -> list[dict]:
        """Build the messages array for the LLM, including system prompt, context, and history."""
        # Build rich context from Runtime
        ctx = context_engine.build_context(user_message)
        context_appendix = ctx.to_system_prompt_appendix()

        tool_defs = kernel.list_capability_definitions()
        available_tools = {
            t["function"]["name"]
            for t in tool_defs
            if t.get("function", {}).get("name")
        }
        prompt_hints = build_prompt_hints(available_tools)

        system_content = SYSTEM_PROMPT
        if prompt_hints:
            system_content += f"\n\n---\n{prompt_hints}"
        if context_appendix:
            system_content += f"\n\n---\n当前用户状态:\n{context_appendix}"

        messages = [{"role": "system", "content": system_content}]

        # Add conversation history. Enforce that every assistant tool_calls
        # is immediately followed by ALL its tool result messages, otherwise
        # strip to avoid DeepSeek API 400 errors.
        history = conversation.get_history()

        # First, tag each message with its parsed tool data
        tagged = []
        for msg in history:
            tc = msg.get("tool_calls")
            tagged.append({
                "role": msg["role"],
                "content": msg["content"] or "",
                "tool_calls": tc,  # already parsed list from conversation.py
                "tool_call_id": msg.get("tool_call_id"),
            })

        # Scan for valid sequences: assistant_with_calls → N×tool_results
        # Mark which indices to keep and which tool_calls to strip
        keep_tool_calls: dict[int, bool] = {}
        keep_tool_result: dict[int, bool] = {}

        i = 0
        while i < len(tagged):
            m = tagged[i]
            if m["role"] == "assistant" and m["tool_calls"]:
                required_ids = {t["id"] for t in m["tool_calls"] if t.get("id")}
                j = i + 1
                satisfied_ids = set()
                # Collect immediately following tool results
                while j < len(tagged) and tagged[j]["role"] == "tool":
                    tid = tagged[j].get("tool_call_id")
                    if tid in required_ids:
                        satisfied_ids.add(tid)
                    j += 1
                if satisfied_ids == required_ids and required_ids:
                    # Valid: keep assistant tool_calls + matching tool results
                    keep_tool_calls[i] = True
                    for k in range(i + 1, j):
                        tid = tagged[k].get("tool_call_id")
                        if tid in required_ids:
                            keep_tool_result[k] = True
                # else: strip tool_calls from this assistant, skip tool results
            i += 1

        # Second pass: build messages respecting the validated structure
        for idx, msg in enumerate(tagged):
            if msg["role"] == "tool":
                if keep_tool_result.get(idx):
                    tool_content = msg["content"] or ""
                    tool_name_guess = ""
                    for tc in tagged:
                        if tc.get("role") == "assistant" and tc.get("tool_calls"):
                            for tcall in tc["tool_calls"]:
                                if tcall.get("id") == msg.get("tool_call_id"):
                                    tool_name_guess = tcall.get("function", {}).get("name", "")
                    if tool_name_guess:
                        tool_content = compact_for_llm(tool_name_guess, tool_content)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": msg["tool_call_id"],
                        "content": tool_content,
                    })
                continue

            item: dict = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "assistant" and msg["tool_calls"] and keep_tool_calls.get(idx):
                item["tool_calls"] = msg["tool_calls"]
            messages.append(item)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

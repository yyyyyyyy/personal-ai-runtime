"""Brain — the core reasoning loop: conversation → tool calls → response.

Brain is stateless. It takes context, calls the LLM, routes tool invocations,
and returns a response. It does NOT own state — that belongs to Runtime.
"""
# mypy: disable-error-code=arg-type

import logging
import time
import uuid
from typing import AsyncIterator

from app.config import settings
from app.core.agents.brain_completion import BrainCompletionMixin
from app.core.agents.conversation import ConversationManager
from app.core.agents.llm_router import llm_router
from app.core.agents.memory_extractor import memory_extractor
from app.core.agents.token_counter import count_message_tokens, count_text_tokens
from app.core.agents.tool_dispatcher import ToolDispatcher
from app.core.agents.tool_markup import (
    parse_tool_calls,
    strip_tool_markup,
)
from app.core.agents.tool_postprocess import canned_summary, compact_for_llm
from app.core.runtime.conversation_recorder import record_conversation_turn
from app.core.runtime.governance.context_pipeline import get_sources
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.taint import taint_registry
from app.core.telemetry.telemetry import LLMCallRecord, telemetry

logger = logging.getLogger(__name__)


class Brain(BrainCompletionMixin):
    """Stateless reasoning engine. One instance per request. Uses LLM Router for multi-provider support."""

    def __init__(self):
        self.client, self.provider = llm_router.get_client()

    async def chat_stream(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
        execution_id: str = "",
        correlation_id: str = "",
    ) -> AsyncIterator[dict]:
        """Process a user message and stream the response.

        system_prompt must be pre-compiled by PromptCompiler before calling Brain.

        correlation_id is used to track the taint chain across tool calls and
        approval recovery. When provided (e.g. from scheduler ExecutionContext),
        it replaces the internally-generated default to keep taint propagation
        consistent (INV-8).
        """
        if not correlation_id:
            correlation_id = f"chat-{uuid.uuid4().hex[:16]}"
        taint_registry.clear(correlation_id)

        # Step 1: Build the messages array
        messages = self._build_messages(conversation, user_message, system_prompt=system_prompt)

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

            # Collect streaming response
            assistant_content = ""
            assistant_content_raw = ""
            assistant_visible = ""  # cleaned text exposed to user
            tool_calls_data: list[dict] = []
            current_tool_call: dict[str, int | str] = {
                "index": -1, "id": "", "function_name": "", "arguments": "",
            }

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text content — always strip markup from full accumulated text.
                # Strip on every delta; emit only new visible portion.
                if delta.content:
                    assistant_content_raw += delta.content
                    cleaned = strip_tool_markup(assistant_content_raw)
                    extra = cleaned[len(assistant_visible) :]
                    if extra:
                        assistant_visible = cleaned
                        yield {"type": "text_delta", "content": extra}

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

            # Recover tool calls leaked as markup in text stream
            if not tool_calls_data and assistant_content_raw:
                parsed, cleaned = parse_tool_calls(assistant_content_raw)
                if parsed:
                    tool_calls_data = parsed
                    assistant_visible = cleaned
                    logger.info(
                        "Recovered %d tool call(s) from markup in text stream",
                        len(parsed),
                    )
            assistant_content = assistant_visible

            # Record LLM call
            llm_latency = (time.time() - llm_start) * 1000
            prompt_tokens = count_message_tokens(messages, model=used_provider.model)
            completion_tokens = count_text_tokens(assistant_content, model=used_provider.model)
            estimated_cost = (
                prompt_tokens * used_provider.price_per_prompt_token
                + completion_tokens * used_provider.price_per_completion_token
            )
            telemetry.record_llm_call(LLMCallRecord(
                provider=used_provider.name,
                model=used_provider.model,
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

            # Process tool calls via ToolDispatcher
            yield {"type": "tool_call_start", "tool_calls": tool_calls_data}

            dispatcher = ToolDispatcher(kernel=kernel, conversation=conversation)
            iteration_tool_results: list[dict] = []
            pending_approval = False

            async for evt in dispatcher.dispatch(
                tool_calls_data,
                correlation_id=correlation_id,
                execution_id=execution_id or "",
            ):
                if evt.get("type") == "_dispatcher_done":
                    iteration_tool_results = evt.get("results", [])
                    # Defer: tool_messages added below (must be after assistant msg)
                    _tool_messages = evt.get("tool_messages", [])
                elif evt.get("type") == "confirmation_required":
                    pending_approval = True
                    yield evt
                elif evt.get("type") == "done":
                    pass
                else:
                    yield evt

            if pending_approval:
                return

            # Persist assistant message with tool calls FIRST
            tc_for_msg = [{
                "id": tc["id"], "type": "function",
                "function": {"name": tc["function_name"], "arguments": tc["arguments"]},
            } for tc in tool_calls_data]

            conversation.save_assistant_message(
                assistant_content or "",
                tool_calls=tc_for_msg if tool_calls_data else None,
            )

            # Build messages: assistant (with tool_calls) → tool results (order matters for LLM)
            messages.extend(dispatcher.build_tool_call_messages(assistant_content, tool_calls_data))
            messages.extend(_tool_messages)

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

        # Step 4: Save + conversation episode
        if full_content and not canned_response_done:
            try:
                sources = get_sources(conversation.conversation_id)
            except Exception:
                sources = None
            conversation.save_assistant_message(full_content, sources=sources)

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

    async def chat(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
    ) -> dict:
        """Non-streaming wrapper for chat_stream (ADR Unification: called by Handler)."""
        content = ""
        pending = False
        pending_tool_name = ""
        pending_tool_args: dict = {}
        pending_approval_id = ""
        conv_id = conversation.conversation_id

        async for event in self.chat_stream(
            conversation, user_message, system_prompt=system_prompt,
        ):
            if event.get("type") == "text_delta" and event.get("content"):
                content += event["content"]
            elif event.get("type") == "confirmation_required":
                pending = True
                pending_tool_name = event.get("tool_name", "")
                pending_tool_args = event.get("tool_args", {})
                pending_approval_id = event.get("approval_id", "")
            elif event.get("type") == "error":
                return {"status": "error", "content": event.get("content", "Unknown error")}

        return {
            "status": "ok",
            "content": content,
            "user_message": user_message,
            "conversation_id": conv_id,
            "pending": pending,
            "tool_name": pending_tool_name,
            "tool_args": pending_tool_args,
            "approval_id": pending_approval_id,
        }

    def _build_messages(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
    ) -> list[dict]:
        """Build the messages array for the LLM.

        system_prompt must be produced by PromptCompiler (artifact + fragments).
        """
        if not system_prompt or not system_prompt.strip():
            raise RuntimeError(
                "system_prompt must be compiled before calling Brain",
            )

        messages = [{"role": "system", "content": system_prompt}]

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
        # Pre-build tool_name lookup from tool_call_id to tool name (O(n) once)
        tool_name_by_id: dict[str, str] = {}
        for tc_msg in tagged:
            if tc_msg.get("role") == "assistant" and tc_msg.get("tool_calls"):
                for tcall in tc_msg["tool_calls"]:
                    if tcall.get("id"):
                        tool_name_by_id[tcall["id"]] = tcall.get("function", {}).get("name", "")

        for idx, msg in enumerate(tagged):
            if msg["role"] == "tool":
                if keep_tool_result.get(idx):
                    tool_content = msg["content"] or ""
                    tool_name_guess = tool_name_by_id.get(msg.get("tool_call_id") or "", "")
                    if tool_name_guess:
                        tool_content = compact_for_llm(tool_name_guess, tool_content)
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

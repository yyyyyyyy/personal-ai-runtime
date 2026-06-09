"""Brain — the core reasoning loop: conversation → tool calls → response.

Brain is stateless. It takes context, calls the LLM, routes tool invocations,
and returns a response. It does NOT own state — that belongs to Runtime.
"""

import json
import time
from typing import AsyncIterator

from app.config import settings
from app.core.agents.context_engine import context_engine
from app.core.agents.conversation import ConversationManager
from app.core.agents.llm_router import llm_router
from app.core.agents.memory_extractor import memory_extractor
from app.core.harness.mcp_hub import mcp_hub
from app.core.runtime.kernel_instance import kernel
from app.core.telemetry.event_recorder import Event, event_recorder
from app.core.telemetry.telemetry import LLMCallRecord, telemetry

SYSTEM_PROMPT = """You are Personal AI OS — a personal AI assistant that helps users manage their life, work, and goals.

You are:
- Helpful: Provide clear, actionable responses.
- Honest: Admit when you don't know something. Never fabricate information.
- Proactive: When you see an opportunity to help with tools, use them.
- Concise: Get to the point. Users value brevity.

You have access to tools. Use them when they would help answer the user's query.
When using tools, briefly explain what you're doing before calling them.

Current context (if available) will include the user's active goals, recent events, and relevant memories.
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
        # Step 1: Build the messages array
        messages = self._build_messages(conversation, user_message)

        # Step 2: Save user message
        conversation.save_user_message(user_message)

        # Step 3: Run the LLM → tool call loop
        full_content = ""
        tool_iterations = 0
        loop_start = time.time()

        while tool_iterations < settings.max_tool_iterations:
            if time.time() - loop_start > settings.total_tool_loop_timeout:
                yield {"type": "error", "content": "Tool call loop timed out."}
                return

            # Call LLM
            llm_start = time.time()
            try:
                response = await self.client.chat.completions.create(
                    model=self.provider.model,
                    messages=messages,
                    tools=mcp_hub.get_tool_defs_for_llm(),
                    tool_choice="auto",
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    stream=True,
                )
            except Exception as e:
                telemetry.record_llm_call(LLMCallRecord(
                    provider=self.provider.name,
                    model=self.provider.model,
                    latency_ms=(time.time() - llm_start) * 1000,
                    success=False,
                    error_message=str(e),
                ))
                yield {"type": "error", "content": f"LLM API error: {str(e)}"}
                return

            # Collect streaming response
            assistant_content = ""
            tool_calls_data: list[dict] = []
            current_tool_call = {"index": -1, "id": "", "function_name": "", "arguments": ""}

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text content
                if delta.content:
                    assistant_content += delta.content
                    yield {"type": "text_delta", "content": delta.content}

                # Tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index is not None and tc.index != current_tool_call["index"]:
                            # New tool call
                            if current_tool_call["index"] >= 0:
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
            if current_tool_call["index"] >= 0:
                tool_calls_data.append(dict(current_tool_call))

            # Record LLM call
            llm_latency = (time.time() - llm_start) * 1000
            prompt_tokens = sum(len(msg.get("content", "")) // 4 for msg in messages)
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
                break

            # Process tool calls
            yield {"type": "tool_call_start", "tool_calls": tool_calls_data}

            # Add assistant message with tool calls to messages
            assistant_msg = {"role": "assistant", "content": assistant_content or None}
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

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

                # Persist tool result
                conversation.save_tool_result(tool_result, tc["id"])

                # Record tool call event
                event_recorder.record(Event(
                    type="tool_call",
                    summary=f"Tool called: {tool_name}",
                    payload={
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result_preview": tool_result[:200],
                    },
                ))

            tool_iterations += 1
            if tool_iterations >= settings.max_tool_iterations:
                # Save any text content the LLM produced in the final iteration
                if assistant_content:
                    conversation.save_assistant_message(assistant_content)
                    full_content = assistant_content
                yield {"type": "error", "content": "达到了最大工具调用次数。已根据当前结果生成回复。"}
                break

        # Step 4: Save final assistant response and record conversation event
        if full_content:
            conversation.save_assistant_message(full_content)

        event_recorder.record(Event(
            type="conversation",
            summary=f"User message: {user_message[:100]}",
            payload={"conversation_id": conversation.conversation_id},
        ))

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

        try:
            response = await self.client.chat.completions.create(
                model=self.provider.model,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except Exception as e:
            err = f"无法生成后续回复: {e}"
            conversation.save_assistant_message(err)
            return err

        content = response.choices[0].message.content or ""
        if content:
            conversation.save_assistant_message(content)
        return content

    def _build_messages(self, conversation: ConversationManager, user_message: str) -> list[dict]:
        """Build the messages array for the LLM, including system prompt, context, and history."""
        # Build rich context from Runtime
        ctx = context_engine.build_context(user_message)
        context_appendix = ctx.to_system_prompt_appendix()

        system_content = SYSTEM_PROMPT
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
                    messages.append({
                        "role": "tool",
                        "tool_call_id": msg["tool_call_id"],
                        "content": msg["content"],
                    })
                continue

            item: dict = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "assistant" and msg["tool_calls"] and keep_tool_calls.get(idx):
                item["tool_calls"] = msg["tool_calls"]
            messages.append(item)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

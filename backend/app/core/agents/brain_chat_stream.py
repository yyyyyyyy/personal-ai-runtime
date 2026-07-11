"""Brain streaming chat loop — extracted from brain.py.

Not counted toward God Object LOC (Architecture Contract only measures
``brain.py`` + ``brain_llm_client.py``).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator

from app.config import settings
from app.core.agents.brain_telemetry import record_llm_call
from app.core.agents.conversation import ConversationManager
from app.core.agents.tool_dispatcher import ToolDispatcher
from app.core.agents.tool_markup import parse_tool_calls, strip_tool_markup
from app.core.agents.tool_postprocess import canned_summary
from app.core.runtime.governance.context_pipeline import get_sources
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.taint import taint_registry

logger = logging.getLogger(__name__)


async def chat_stream(
    brain,
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
    messages = brain._build_messages(conversation, user_message, system_prompt=system_prompt)

    # Step 2: Save user message
    conversation.save_user_message(user_message)

    # Step 3: Run the LLM → tool call loop
    full_content = ""
    canned_response_done = False
    tool_iterations = 0
    cumulative_prompt_tokens = 0
    loop_start = time.time()

    while tool_iterations < settings.max_tool_iterations:
        if time.time() - loop_start > settings.total_tool_loop_timeout:
            yield {"type": "error", "content": "Tool call loop timed out."}
            return
        if cumulative_prompt_tokens >= settings.max_tool_loop_prompt_tokens:
            note = "\n\n（已达本轮工具调用的 token 上限，以上为根据已收集信息生成的回复。）"
            yield {"type": "text_delta", "content": note}
            full_content += note
            break

        # Call LLM (with multi-provider fallback)
        llm_start = time.time()
        try:
            response, client, used_provider = await brain._llm.create_stream(messages)
        except Exception as e:
            yield {"type": "error", "content": f"LLM API error: {str(e)}"}
            return
        if used_provider.name != brain._llm.provider.name:
            brain._llm.replace_provider(client, used_provider)

        # Collect streaming response — token-level text deltas are yielded
        # directly here so SSE streaming stays live. Tool-call assembly and
        # markup-recovery logic lives inline because it interleaves with yields.
        assistant_content = ""
        assistant_content_raw = ""
        assistant_visible = ""  # cleaned text exposed to user
        tool_calls_data: list[dict] = []
        current_tool_call: dict[str, int | str] = {
            "index": -1, "id": "", "function_name": "", "arguments": "",
        }
        # Providers that honour stream_options return token usage on the
        # final chunk. Default to None and fall back to tiktoken below.
        stream_usage: Any = None

        async for chunk in response:
            # Capture usage from the terminal chunk when the provider
            # includes it (OpenAI, DeepSeek).
            if getattr(chunk, "usage", None) is not None:
                stream_usage = chunk.usage
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

        # Record LLM call telemetry (latency, tokens, cost).
        turn_tokens = record_llm_call(
            messages, assistant_content, llm_start,
            provider_name=used_provider.name,
            provider_model=used_provider.model,
            price_per_prompt_token=used_provider.price_per_prompt_token,
            price_per_completion_token=used_provider.price_per_completion_token,
            usage=stream_usage,
        )
        cumulative_prompt_tokens += turn_tokens

        # If LLM returned a text response without tool calls
        if not tool_calls_data:
            full_content = assistant_content
            if not full_content.strip():
                full_content = await brain._llm.complete_text_only(messages, user_message)
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
                synthesized = await brain._llm.synthesize_from_tool_results(messages)
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

    yield {"type": "done"}

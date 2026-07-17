"""Brain streaming chat loop — extracted from brain.py.

Not counted toward God Object LOC (Architecture Contract only measures
``brain.py`` + ``brain_llm_client.py``).

Stream chunk assembly lives in ``brain_stream_assemble``; this module owns
the LLM → tool → continue control loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator

from app.config import settings
from app.core.agents.brain_stream_assemble import AssembledStream, iter_assembled_stream
from app.core.agents.brain_telemetry import record_llm_call
from app.core.agents.conversation import ConversationManager
from app.core.agents.tool_dispatcher import ToolDispatcher
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
    conversation.correlation_id = correlation_id

    messages = brain._build_messages(conversation, user_message, system_prompt=system_prompt)
    conversation.save_user_message(user_message)

    full_content = ""
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

        llm_start = time.time()
        try:
            response, client, used_provider = await brain._llm.create_stream(messages)
        except Exception as e:
            yield {"type": "error", "content": f"LLM API error: {str(e)}"}
            return
        if used_provider.name != brain._llm.provider.name:
            brain._llm.replace_provider(client, used_provider)

        assembled: AssembledStream | None = None
        async for evt in iter_assembled_stream(response):
            if evt.get("type") == "_stream_assembled":
                assembled = evt["result"]
            else:
                yield evt

        if assembled is None:
            yield {"type": "error", "content": "LLM stream ended without a result."}
            return

        assistant_content = assembled.visible_text
        tool_calls_data = assembled.tool_calls

        turn_tokens = record_llm_call(
            messages, assistant_content, llm_start,
            provider_name=used_provider.name,
            provider_model=used_provider.model,
            price_per_prompt_token=used_provider.price_per_prompt_token,
            price_per_completion_token=used_provider.price_per_completion_token,
            usage=assembled.usage,
        )
        cumulative_prompt_tokens += turn_tokens

        if not tool_calls_data:
            full_content = assistant_content
            if not full_content.strip() and user_message.strip():
                # Second LLM pass only when the first stream was empty — skip
                # whitespace-only user turns to avoid burning tokens on noise.
                try:
                    full_content = await asyncio.wait_for(
                        brain._llm.complete_text_only(messages, user_message),
                        timeout=settings.complete_text_only_timeout,
                    )
                except TimeoutError:
                    logger.warning("complete_text_only timed out")
                    full_content = ""
                if full_content:
                    yield {"type": "text_delta", "content": full_content}
            break

        yield {"type": "tool_call_start", "tool_calls": tool_calls_data}

        dispatcher = ToolDispatcher(kernel=kernel, conversation=conversation)
        iteration_tool_results: list[dict] = []
        pending_approval = False
        _tool_messages: list[dict] = []

        async for evt in dispatcher.dispatch(
            tool_calls_data,
            correlation_id=correlation_id,
            execution_id=execution_id or "",
        ):
            if evt.get("type") == "_dispatcher_done":
                iteration_tool_results = evt.get("results", [])
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

        tc_for_msg = [{
            "id": tc["id"], "type": "function",
            "function": {"name": tc["function_name"], "arguments": tc["arguments"]},
        } for tc in tool_calls_data]

        conversation.save_assistant_message(
            assistant_content or "",
            tool_calls=tc_for_msg if tool_calls_data else None,
        )

        messages.extend(dispatcher.build_tool_call_messages(assistant_content, tool_calls_data))
        messages.extend(_tool_messages)

        summary = canned_summary(tool_calls_data, iteration_tool_results)
        if summary:
            full_content = summary
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

    if full_content:
        try:
            sources = get_sources(conversation.conversation_id)
        except Exception:
            sources = None
        conversation.save_assistant_message(full_content, sources=sources)

    yield {"type": "done"}

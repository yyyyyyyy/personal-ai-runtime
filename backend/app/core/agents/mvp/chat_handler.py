"""Chat Handler — processes chat messages via Scheduler with streaming (ADR Unification).

Stage 3: PromptCompiler builds the system prompt from Universal Fragments
(RuntimeIdentity + ConversationState + Memory + Knowledge) via QueryAnalysis.

ChatTextDelta events are pushed to the SSE queue registry instead of event_log
to avoid polluting the immutable Truth Layer with high-frequency incremental
text chunks (e.g. 1-2 character deltas from token-level LLM streaming).
Only ChatCompleted and ChatDone are recorded in event_log.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


@subscribe("ChatRequested")
async def on_chat_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Process a chat message with streaming.

    Stage 3: PromptCompiler builds the system prompt from Universal Fragments.
    Brain receives the pre-built system_prompt.
    """
    from app.chat.prompt_compiler import CompileContext, prompt_compiler
    from app.core.agents.brain import Brain
    from app.core.agents.conversation import ConversationManager
    from app.core.runtime.sse_queue_registry import push

    user_message = event.payload.get("user_message", "")
    conv_id = event.payload.get("conversation_id", "")

    if not user_message:
        return

    system_prompt = await prompt_compiler.compile(
        CompileContext(
            conversation_id=conv_id,
            execution_id=ctx.execution_id,
            user_message=user_message,
            stage="chat",
        ),
    )

    brain = Brain()
    conversation = ConversationManager(conversation_id=conv_id)

    content = ""
    pending = False
    pending_data: dict = {}
    error_content = ""

    async for evt in brain.chat_stream(
        conversation, user_message,
        execution_id=ctx.execution_id,
        correlation_id=ctx.correlation_id,
        system_prompt=system_prompt,
    ):
        if evt.get("type") == "text_delta" and evt.get("content"):
            content += evt["content"]
            # Push text delta to SSE queue (NOT event_log) for near-zero-latency streaming.
            await push(ctx.correlation_id, {
                "type": "text_delta",
                "content": evt["content"],
            })
        elif evt.get("type") == "confirmation_required":
            pending = True
            pending_data = {
                "tool_name": evt.get("tool_name", ""),
                "tool_args": evt.get("tool_args", {}),
                "tool_call_id": evt.get("tool_call_id", ""),
                "approval_id": evt.get("approval_id", ""),
            }
        elif evt.get("type") == "done":
            pass
        elif evt.get("type") == "error":
            error_content = evt.get("content", "Error")
            break

    result = {
        "status": "ok" if not error_content else "error",
        "content": content,
        "user_message": user_message,
        "conversation_id": conv_id,
        "pending": pending,
        "tool_name": pending_data.get("tool_name", ""),
        "tool_args": pending_data.get("tool_args", {}),
        "approval_id": pending_data.get("approval_id", ""),
        "tool_call_id": pending_data.get("tool_call_id", ""),
    }

    # Emit ChatCompleted to event_log (immutable Truth Layer — one record per turn).
    ctx.emit(
        "ChatCompleted", "chat", f"chat_{conv_id}",
        payload=result,
        caused_by=event.id,
    )

    ctx.emit(
        "ChatDone", "chat", f"chat_{conv_id}",
        payload={"conversation_id": conv_id},
        caused_by=event.id,
    )

    # Signal SSE stream to close (fast path via queue; fallback via event_log polling).
    if error_content:
        await push(ctx.correlation_id, {"type": "error", "content": error_content})
    else:
        await push(ctx.correlation_id, {"type": "done", "result": result})

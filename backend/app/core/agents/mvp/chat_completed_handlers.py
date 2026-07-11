"""ChatCompleted event handlers — memory extraction and turn recording.

These were previously called synchronously inside Brain.chat_stream().
Moving them to @subscribe handlers driven by the ChatCompleted event makes
them properly event-sourced: they are reactions to the immutable truth that
a chat turn completed, not side effects baked into the reasoning loop.
"""

from __future__ import annotations

import logging

from app.core.agents.memory_extractor import memory_extractor
from app.core.runtime.handler_registry import subscribe
from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


def _kernel():
    from app.core.runtime import kernel_instance

    return kernel_instance.kernel


def _preview(user_message: str, assistant_message: str) -> str:
    parts = [f"User: {user_message[:240]}"]
    if assistant_message:
        parts.append(f"Assistant: {assistant_message[:240]}")
    return "\n".join(parts)[:500]


def record_conversation_turn(
    conversation_id: str,
    user_message: str,
    assistant_message: str = "",
    *,
    actor: str = "user",
    caused_by: str | None = None,
) -> Event:
    """Append ConversationRecorded to the Event Log; return the emitted event."""
    import uuid

    correlation_id = f"conv-turn-{uuid.uuid4().hex[:16]}"
    payload = {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "preview": _preview(user_message, assistant_message),
    }
    return _kernel().emit_event(
        "ConversationRecorded",
        "conversation",
        conversation_id,
        payload=payload,
        actor=actor,
        correlation_id=correlation_id,
        caused_by=caused_by,
    )


@subscribe("ChatCompleted")
async def on_chat_completed_record_turn(_ctx, event):
    """Emit ConversationRecorded for every completed chat turn."""
    payload = event.payload if isinstance(event.payload, dict) else {}
    conv_id = payload.get("conversation_id", "")
    user_message = payload.get("user_message", "")
    assistant_content = payload.get("content", "")
    if conv_id and (user_message or assistant_content):
        try:
            record_conversation_turn(conv_id, user_message, assistant_content)
        except Exception:
            logger.exception("record_conversation_turn failed for conv=%s", conv_id)


@subscribe("ChatCompleted")
async def on_chat_completed_extract_memories(_ctx, event):
    """Fire-and-forget memory extraction after every completed chat turn."""
    payload = event.payload if isinstance(event.payload, dict) else {}
    conv_id = payload.get("conversation_id", "")
    user_message = payload.get("user_message", "")
    assistant_content = payload.get("content", "")
    if conv_id and (user_message or assistant_content):
        memory_extractor.schedule(
            f"User: {user_message}\nAssistant: {assistant_content}",
            source=f"conv:{conv_id}",
        )

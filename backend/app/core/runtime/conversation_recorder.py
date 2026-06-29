"""Conversation Recorder — Experience Episodes into event_log.

ConversationRecorded events are immutable Experience representations of a
user↔assistant turn. They feed Trajectory linking and review surfaces without
replacing the operational `messages` table (UI/chat history).
"""

from __future__ import annotations

import uuid

from app.core.runtime.kernel.event import Event


def _kernel():
    from app.core.runtime import kernel_instance

    return kernel_instance.kernel


def record_conversation_turn(
    conversation_id: str,
    user_message: str,
    assistant_message: str = "",
    *,
    actor: str = "user",
    caused_by: str | None = None,
) -> Event:
    """Append ConversationRecorded to the Event Log; return the emitted event.

    Args:
        caused_by: Optional event id of the ChatCompleted that triggered this recording.
    """
    correlation_id = f"conv-turn-{uuid.uuid4().hex[:16]}"
    payload = {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "preview": _preview(user_message, assistant_message),
    }
    event = _kernel().emit_event(
        "ConversationRecorded",
        "conversation",
        conversation_id,
        payload=payload,
        actor=actor,
        correlation_id=correlation_id,
        caused_by=caused_by,
    )

    return event


def _preview(user_message: str, assistant_message: str) -> str:
    parts = [f"User: {user_message[:240]}"]
    if assistant_message:
        parts.append(f"Assistant: {assistant_message[:240]}")
    return "\n".join(parts)[:500]

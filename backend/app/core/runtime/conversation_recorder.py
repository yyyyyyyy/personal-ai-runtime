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
) -> Event:
    """Append ConversationRecorded to the Event Log; return the emitted event."""
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
    )

    from app.config import settings

    if settings.experimental_trajectory_enabled:
        from app.experimental.trajectory.suggester import trajectory_suggester

        text = f"User: {user_message}\nAssistant: {assistant_message}".strip()
        trajectory_suggester.schedule_after_conversation(
            event.seq,
            text,
            source=conversation_id,
        )
    return event


def _preview(user_message: str, assistant_message: str) -> str:
    parts = [f"User: {user_message[:240]}"]
    if assistant_message:
        parts.append(f"Assistant: {assistant_message[:240]}")
    return "\n".join(parts)[:500]

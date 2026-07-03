"""ChatCompleted event handlers — memory extraction and turn recording.

These were previously called synchronously inside Brain.chat_stream().
Moving them to @subscribe handlers driven by the ChatCompleted event makes
them properly event-sourced: they are reactions to the immutable truth that
a chat turn completed, not side effects baked into the reasoning loop.
"""

from __future__ import annotations

import logging

from app.core.agents.memory_extractor import memory_extractor
from app.core.runtime.conversation_recorder import record_conversation_turn
from app.core.runtime.handler_registry import subscribe

logger = logging.getLogger(__name__)


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

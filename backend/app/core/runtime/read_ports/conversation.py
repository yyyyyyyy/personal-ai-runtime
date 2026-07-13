"""Conversation / message projection read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def query_conversation_messages(
    conversation_id: str,
    *,
    limit: int = 20,
    order: str = "created_at_desc",
) -> list[dict[str, Any]]:
    return kernel().query_state(
        "messages",
        conversation_id=conversation_id,
        limit=limit,
        order=order,
    )


def query_conversation(conversation_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("conversations", id=conversation_id, limit=1)
    return rows[0] if rows else None


def query_conversations(*, limit: int = 50) -> list[dict[str, Any]]:
    return kernel().query_state("conversations", limit=limit)


def query_message(message_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("messages", id=message_id, limit=1)
    return rows[0] if rows else None


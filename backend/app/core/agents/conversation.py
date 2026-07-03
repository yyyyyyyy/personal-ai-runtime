"""Multi-turn conversation management with sliding window strategy.

All writes go through Kernel events (Conversation* / MessageAppended).
The conversations and messages tables are projections, not source of truth.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config import settings
from app.core.agents.tool_markup import strip_tool_markup
from app.core.runtime.kernel_instance import kernel as default_kernel


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ConversationManager:
    """Manages conversation lifecycle, message persistence, and context window."""

    conversation_id: str
    kernel: object = field(default=None, repr=False)

    def _k(self):
        return self.kernel or default_kernel

    def get_history(self, *, since_created_at: str | None = None) -> list[dict]:
        """Get recent messages within the sliding window.

        If since_created_at is provided, only return messages created after
        that timestamp (enables incremental fetching for long conversations).
        """
        messages = self._k().query_state(
            "messages",
            conversation_id=self.conversation_id,
            limit=settings.max_recent_messages,
            order="created_at_asc",
        )
        result = []
        for msg in messages:
            if since_created_at and msg["created_at"] <= since_created_at:
                continue
            item = {"role": msg["role"], "content": msg["content"]}
            if msg["tool_calls"]:
                try:
                    item["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if msg["tool_call_id"]:
                item["tool_call_id"] = msg["tool_call_id"]
            result.append(item)
        return result

    def save_message(
        self,
        role: str,
        content: str,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
        sources: list | None = None,
    ) -> dict:
        """Persist a message via MessageAppended event."""
        if role == "assistant" and content:
            content = strip_tool_markup(content)
        msg_id = str(uuid.uuid4())
        tc_json = tool_calls if tool_calls is None else tool_calls
        payload: dict = {
            "message_id": msg_id,
            "role": role,
            "content": content,
            "tool_calls": tc_json,
            "tool_call_id": tool_call_id,
            "created_at": _now(),
        }
        if sources:
            payload["sources"] = sources
        self._k().emit_event(
            "MessageAppended",
            "conversation",
            self.conversation_id,
            payload=payload,
            actor="user",
        )
        return db.get_message(msg_id) or {
            "id": msg_id,
            "conversation_id": self.conversation_id,
            "role": role,
            "content": content,
        }

    def save_user_message(self, content: str) -> dict:
        return self.save_message(role="user", content=content)

    def save_assistant_message(
        self, content: str, tool_calls: list | None = None, sources: list | None = None
    ) -> dict:
        return self.save_message(
            role="assistant", content=content, tool_calls=tool_calls, sources=sources
        )

    def save_tool_result(self, content: str, tool_call_id: str) -> dict:
        return self.save_message(role="tool", content=content, tool_call_id=tool_call_id)

    def save_system_message(self, content: str) -> dict:
        return self.save_message(role="system", content=content)


@dataclass
class ConversationAPI:
    """Stateless API for conversation CRUD operations."""

    @staticmethod
    def create(title: str | None = None, *, kernel=None) -> dict:
        k = kernel or default_kernel
        conv_id = str(uuid.uuid4())
        now = _now()
        k.emit_event(
            "ConversationCreated",
            "conversation",
            conv_id,
            payload={"title": title or "New Conversation", "created_at": now},
            actor="user",
        )
        return db.get_conversation(conv_id) or {
            "id": conv_id,
            "title": title or "New Conversation",
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get(conv_id: str) -> dict | None:
        return db.get_conversation(conv_id)

    @staticmethod
    def list_all(limit: int = 50) -> list[dict]:
        return db.list_conversations(limit=limit)

    @staticmethod
    def delete(conv_id: str, *, kernel=None):
        k = kernel or default_kernel
        k.emit_event(
            "ConversationDeleted",
            "conversation",
            conv_id,
            payload={},
            actor="user",
        )

    @staticmethod
    def update(conv_id: str, title: str | None = None, summary: str | None = None, *, kernel=None):
        k = kernel or default_kernel
        payload: dict = {}
        if title is not None:
            payload["title"] = title
        if summary is not None:
            payload["summary"] = summary
        if not payload:
            return
        k.emit_event(
            "ConversationUpdated",
            "conversation",
            conv_id,
            payload=payload,
            actor="user",
        )

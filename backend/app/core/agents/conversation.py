"""Multi-turn conversation management with sliding window strategy."""

import json
from dataclasses import dataclass

from app.config import settings
from app.store.database import db


@dataclass
class ConversationManager:
    """Manages conversation lifecycle, message persistence, and context window."""

    conversation_id: str

    def get_history(self) -> list[dict]:
        """Get recent messages within the sliding window."""
        messages = db.get_recent_messages(self.conversation_id, limit=settings.max_recent_messages)
        result = []
        for msg in messages:
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

    def save_message(self, role: str, content: str, tool_calls: list | None = None, tool_call_id: str | None = None) -> dict:
        """Persist a message to the database."""
        tc_json = json.dumps(tool_calls) if tool_calls else None
        return db.add_message(
            conv_id=self.conversation_id,
            role=role,
            content=content,
            tool_calls=tc_json,
            tool_call_id=tool_call_id,
        )

    def save_user_message(self, content: str) -> dict:
        return self.save_message(role="user", content=content)

    def save_assistant_message(self, content: str, tool_calls: list | None = None) -> dict:
        return self.save_message(role="assistant", content=content, tool_calls=tool_calls)

    def save_tool_result(self, content: str, tool_call_id: str) -> dict:
        return self.save_message(role="tool", content=content, tool_call_id=tool_call_id)

    def save_system_message(self, content: str) -> dict:
        return self.save_message(role="system", content=content)


@dataclass
class ConversationAPI:
    """Stateless API for conversation CRUD operations."""

    @staticmethod
    def create(title: str | None = None) -> dict:
        return db.create_conversation(title=title)

    @staticmethod
    def get(conv_id: str) -> dict | None:
        return db.get_conversation(conv_id)

    @staticmethod
    def list_all(limit: int = 50) -> list[dict]:
        return db.list_conversations(limit=limit)

    @staticmethod
    def delete(conv_id: str):
        db.delete_conversation(conv_id)

    @staticmethod
    def update(conv_id: str, title: str | None = None, summary: str | None = None):
        db.update_conversation(conv_id, title=title, summary=summary)

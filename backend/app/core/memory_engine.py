"""Memory Engine — extracts, stores, and retrieves user memories.

Memories are NOT raw data. They are refined insights from Events and conversations.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from app.store.database import db
from app.store.vector import vector_store


class MemoryEngine:
    """Manages the complete lifecycle of user memories."""

    def store_memory(
        self,
        content: str,
        category: str = "fact",
        source: str | None = None,
    ) -> str:
        """Store a memory in both SQLite and ChromaDB.

        Args:
            content: The memory content/insight
            category: One of 'profile', 'preference', 'fact', 'knowledge'
            source: What triggered this memory (conversation_id, event_id, etc.)
        """
        memory_id = str(uuid.uuid4())

        # Store embedding in ChromaDB
        embedding_id = vector_store.add_memory(
            content=content,
            metadata={"category": category, "source": source or ""},
            memory_id=memory_id,
        )

        # Store structured record in SQLite
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO memories (id, category, content, source, embedding_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (memory_id, category, content, source, embedding_id, datetime.utcnow().isoformat()),
            )

        return memory_id

    def search_relevant_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search for memories relevant to the current context."""
        return vector_store.search_memories(query, n_results=n_results)

    def retrieve_context_string(self, query: str, max_memories: int = 3) -> str:
        """Build a context string from relevant memories for injection into the LLM prompt.

        Returns an empty string if no relevant memories found.
        """
        memories = self.search_relevant_memories(query, n_results=max_memories)
        if not memories:
            return ""

        lines = ["## 相关记忆"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"{i}. {mem['content']}")
        return "\n".join(lines)

    def list_memories(self, category: str | None = None, limit: int = 50) -> list[dict]:
        """List stored memories, optionally filtered by category."""
        with db.get_db() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, memory_id: str):
        """Delete a memory from both SQLite and ChromaDB."""
        with db.get_db() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        vector_store.delete_memory(memory_id)

    def update_memory(self, memory_id: str, content: str, category: str | None = None):
        """Update an existing memory."""
        with db.get_db() as conn:
            fields = ["content = ?", "updated_at = ?"]
            params = [content, datetime.utcnow().isoformat()]
            if category:
                fields.append("category = ?")
                params.append(category)
            params.append(memory_id)
            conn.execute(
                f"UPDATE memories SET {', '.join(fields)} WHERE id = ?", params
            )


memory_engine = MemoryEngine()

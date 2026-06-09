"""Memory Engine — extracts, stores, and retrieves user memories.

Memories are NOT raw data. They are refined insights from Events and conversations.
All writes to the `memories` projection go through the Kernel (MemoryDerived/Updated/Deleted).
ChromaDB is a derived search index updated alongside projection events.
"""

import uuid

from app.core.runtime.kernel_instance import kernel
from app.store.vector import vector_store


class MemoryEngine:
    """Manages the complete lifecycle of user memories."""

    def store_memory(
        self,
        content: str,
        category: str = "fact",
        source: str | None = None,
        actor: str = "user",
        confidence: float = 0.5,
    ) -> str:
        """Store a memory via Kernel event + ChromaDB index."""
        memory_id = str(uuid.uuid4())

        embedding_id = vector_store.add_memory(
            content=content,
            metadata={"category": category, "source": source or ""},
            memory_id=memory_id,
        )

        kernel.emit_event(
            type="MemoryDerived",
            aggregate_type="memory",
            aggregate_id=memory_id,
            payload={
                "category": category,
                "content": content,
                "source": source or "",
                "embedding_id": embedding_id,
                "confidence": confidence,
            },
            actor=actor,
        )
        return memory_id

    def search_relevant_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search for memories relevant to the current context."""
        return kernel.recall_memory(query, k=n_results)

    def retrieve_context_string(self, query: str, max_memories: int = 3) -> str:
        """Build a context string from relevant memories for injection into the LLM prompt."""
        memories = self.search_relevant_memories(query, n_results=max_memories)
        if not memories:
            return ""

        lines = ["## 相关记忆"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"{i}. {mem['content']}")
        return "\n".join(lines)

    def list_memories(self, category: str | None = None, limit: int = 50) -> list[dict]:
        """List stored memories via Kernel read ABI."""
        filters: dict = {"limit": limit}
        if category:
            filters["category"] = category
        return kernel.query_state("memories", **filters)

    def delete_memory(self, memory_id: str, actor: str = "user") -> None:
        """Delete a memory via Kernel event + ChromaDB index."""
        vector_store.delete_memory(memory_id)
        kernel.emit_event(
            type="MemoryDeleted",
            aggregate_type="memory",
            aggregate_id=memory_id,
            actor=actor,
        )

    def update_memory(
        self,
        memory_id: str,
        content: str,
        category: str | None = None,
        actor: str = "user",
    ) -> None:
        """Update an existing memory via Kernel event + refresh vector index."""
        vector_store.delete_memory(memory_id)
        embedding_id = vector_store.add_memory(
            content=content,
            metadata={"category": category or "fact"},
            memory_id=memory_id,
        )
        payload: dict = {"content": content, "embedding_id": embedding_id}
        if category is not None:
            payload["category"] = category
        kernel.emit_event(
            type="MemoryUpdated",
            aggregate_type="memory",
            aggregate_id=memory_id,
            payload=payload,
            actor=actor,
        )


memory_engine = MemoryEngine()

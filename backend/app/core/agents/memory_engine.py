"""Memory Engine — extracts, stores, and retrieves user memories.

Memories are NOT raw data. They are refined insights from Events and conversations.
All writes to the `memories` projection go through the Kernel (MemoryDerived/Updated/Deleted).
ChromaDB is a derived search index maintained by the Kernel after projection.
"""

import uuid
from typing import TYPE_CHECKING

from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_container import _LazyProxy, runtime


class MemoryEngine:
    """Manages the complete lifecycle of user memories."""

    def store_memory(
        self,
        content: str,
        category: str = "fact",
        source: str | None = None,
        actor: str = "user",
        confidence: float = 0.5,
        source_document_id: str | None = None,
        source_document_name: str | None = None,
    ) -> str:
        """Store a memory via Kernel event; Chroma index syncs in Kernel Space.

        When the memory was derived from a knowledge-base document (e.g. the
        user discussed an uploaded PDF and the extractor captured a fact from
        that discussion), pass source_document_id / source_document_name to
        record the provenance link. The frontend can then show "derived from:
        <doc>" and jump to the document.
        """
        memory_id = str(uuid.uuid4())
        payload: dict[str, object] = {
            "category": category,
            "content": content,
            "source": source or "",
            "confidence": confidence,
        }
        if source_document_id:
            payload["source_document_id"] = source_document_id
        if source_document_name:
            payload["source_document_name"] = source_document_name

        kernel.emit_event(
            type="MemoryDerived",
            aggregate_type="memory",
            aggregate_id=memory_id,
            payload=payload,
            actor=actor,
        )
        return memory_id

    def search_relevant_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search for memories relevant to the current context."""
        return kernel.recall_memory(query, k=n_results)

    def _enrich_recall_hits(self, hits: list[dict]) -> list[dict]:
        """Join Chroma recall hits with governed projection fields (origin, confidence)."""
        enriched: list[dict] = []
        for hit in hits:
            memory_id = hit.get("id")
            if not memory_id:
                continue
            row = read_ports.query_memory(memory_id)
            if not row:
                continue
            enriched.append({
                "id": memory_id,
                "content": row.get("content") or hit.get("content", ""),
                "confidence": float(row.get("confidence") or 0.5),
            })
        return enriched

    def format_memory_context(self, memories: list[dict]) -> str:
        """Render memories for LLM context injection."""
        if not memories:
            return ""

        lines = ["## 相关记忆"]
        for i, mem in enumerate(memories, 1):
            conf = mem.get("confidence", 0.5)
            lines.append(f"{i}. [置信度 {conf:.2f}] {mem['content']}")
        return "\n".join(lines)

    def retrieve_context_string(self, query: str, max_memories: int = 3) -> str:
        """Build a context string from relevant memories for injection into the LLM prompt."""
        hits = self.search_relevant_memories(query, n_results=max_memories)
        enriched = self._enrich_recall_hits(hits)
        return self.format_memory_context(enriched)

    def list_memories(self, category: str | None = None, limit: int = 50) -> list[dict]:
        """List stored memories via read_ports."""
        return read_ports.query_memories(category=category, limit=limit)

    def delete_memory(self, memory_id: str, actor: str = "user") -> None:
        """Delete a memory via Kernel event; Chroma index syncs in Kernel Space."""
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
        """Update an existing memory via Kernel event; Chroma index syncs in Kernel Space."""
        payload: dict = {"content": content}
        if category is not None:
            payload["category"] = category
        kernel.emit_event(
            type="MemoryUpdated",
            aggregate_type="memory",
            aggregate_id=memory_id,
            payload=payload,
            actor=actor,
        )


if TYPE_CHECKING:
    memory_engine: MemoryEngine
else:
    memory_engine = _LazyProxy(lambda: runtime.memory_engine)

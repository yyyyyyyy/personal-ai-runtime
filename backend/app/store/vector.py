"""ChromaDB vector store management for semantic search and memory."""

import os
import uuid

# Suppress ChromaDB telemetry before the chromadb import touches posthog
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")

# Monkey-patch posthog to prevent capture() signature incompatibility
import posthog  # noqa: E402


# Monkey-patch posthog to prevent capture() from breaking tests/CI (signature bugs, recursion).
def _safe_capture(*args, **kwargs):
    return None


posthog.capture = _safe_capture

import chromadb  # noqa: E402
from chromadb.config import Settings as ChromaSettings  # noqa: E402

from app.config import settings  # noqa: E402


class VectorStore:
    """Manages ChromaDB collections for memory and knowledge embeddings."""

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.vector_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._init_collections()

    def _init_collections(self):
        """Create collections if they don't exist."""
        self.memory_collection = self.client.get_or_create_collection(
            name="memories",
            metadata={"description": "Long-term user memories and preferences"},
        )
        self.knowledge_collection = self.client.get_or_create_collection(
            name="knowledge",
            metadata={"description": "Imported documents and knowledge fragments"},
        )

    def add_memory(
        self, content: str, metadata: dict | None = None, memory_id: str | None = None
    ) -> str:
        """Store a memory with embedding. Returns the embedding ID."""
        mid = memory_id or str(uuid.uuid4())
        self.memory_collection.add(
            ids=[mid],
            documents=[content],
            metadatas=[metadata or {}],
        )
        return mid

    def index_memory(
        self, content: str, metadata: dict | None = None, memory_id: str | None = None
    ) -> str:
        """MemoryIndexPort implementation — idempotent index per memory_id.

        Delegates to add_memory but first removes any existing entry for the
        same memory_id so re-indexing (e.g. on MemoryUpdated) doesn't create
        duplicate embeddings.
        """
        if memory_id:
            try:
                self.memory_collection.delete(ids=[memory_id])
            except Exception:
                pass  # not present yet — fine
        return self.add_memory(content, metadata=metadata, memory_id=memory_id)

    def search_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search for related memories."""
        batch = self.search_memories_batch([query], n_results=n_results)
        return batch[0] if batch else []

    def search_memories_batch(
        self, queries: list[str], n_results: int = 5
    ) -> list[list[dict]]:
        """Batch semantic search — one Chroma round-trip for many queries.

        Returns a list aligned with ``queries``; each entry is the hit list
        for that query (same shape as :meth:`search_memories`).
        """
        if not queries:
            return []
        results = self.memory_collection.query(
            query_texts=queries,
            n_results=n_results,
        )
        batches: list[list[dict]] = []
        ids_by_q = results.get("ids") or []
        docs_by_q = results.get("documents") or []
        metas_by_q = results.get("metadatas") or []
        dists_by_q = results.get("distances") or []
        for q_idx in range(len(queries)):
            items: list[dict] = []
            if q_idx < len(ids_by_q) and ids_by_q[q_idx]:
                for i in range(len(ids_by_q[q_idx])):
                    items.append({
                        "id": ids_by_q[q_idx][i],
                        "content": docs_by_q[q_idx][i] if docs_by_q and docs_by_q[q_idx] else "",
                        "metadata": (
                            metas_by_q[q_idx][i] if metas_by_q and metas_by_q[q_idx] else {}
                        ),
                        "distance": (
                            dists_by_q[q_idx][i] if dists_by_q and dists_by_q[q_idx] else None
                        ),
                    })
            batches.append(items)
        return batches

    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search in the knowledge base."""
        results = self.knowledge_collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        items = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })
        return items

    def add_knowledge_chunk(
        self, content: str, metadata: dict | None = None, chunk_id: str | None = None
    ) -> str:
        """Store a knowledge chunk with embedding."""
        cid = chunk_id or str(uuid.uuid4())
        self.knowledge_collection.add(
            ids=[cid],
            documents=[content],
            metadatas=[metadata or {}],
        )
        return cid

    def delete_memory(self, memory_id: str):
        """Delete a memory by its ID."""
        self.memory_collection.delete(ids=[memory_id])

    def delete_knowledge_chunks(self, chunk_ids: list[str]):
        """Delete knowledge chunks by their IDs."""
        if chunk_ids:
            self.knowledge_collection.delete(ids=chunk_ids)


from app.core.runtime.runtime_container import _LazyProxy, runtime  # noqa: E402

vector_store = _LazyProxy(lambda: runtime.vector_store)

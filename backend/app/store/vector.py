"""ChromaDB vector store management for semantic search and memory."""

import os
import uuid
from typing import Any, TypedDict


class VectorSearchResult(TypedDict):
    id: str
    content: str
    metadata: dict[str, Any]
    distance: float | None


# Suppress ChromaDB telemetry before the chromadb import touches posthog
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")

# Optional: older Chroma builds pulled posthog; patch capture if present.
try:
    import posthog  # noqa: E402
except ImportError:
    posthog = None  # type: ignore[assignment]
else:
    def _safe_capture(*args: Any, **kwargs: Any) -> None:
        return None

    posthog.capture = _safe_capture  # type: ignore[assignment]

import chromadb  # noqa: E402
from chromadb.config import Settings as ChromaSettings  # noqa: E402
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction  # noqa: E402

# Pin the same default ONNX MiniLM L6 v2 path Chroma 0.5.x / 1.x ships so
# upgrades do not silently switch embedding models or dimensions.
# Typed as Any: chromadb stubs expect a broader EmbeddingFunction protocol than
# DefaultEmbeddingFunction declares.
_EMBEDDING_FUNCTION: Any = DefaultEmbeddingFunction()


class VectorStore:
    """Manages ChromaDB collections for memory and knowledge embeddings."""

    def __init__(self):
        # Resolve settings at call time so test reset_settings() takes effect.
        from app.config import settings

        self.client = chromadb.PersistentClient(
            path=settings.vector_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._init_collections()

    def _init_collections(self):
        """Create collections if they don't exist."""
        # Cosine space matches distance→weight conversion in read_ports
        # (weight ≈ 1 - distance). Fresh installs only — no migration path.
        hnsw_config = {"hnsw:space": "cosine"}
        self.memory_collection = self.client.get_or_create_collection(
            name="memories",
            embedding_function=_EMBEDDING_FUNCTION,
            metadata={
                "description": "Long-term user memories and preferences",
                **hnsw_config,
            },
        )
        self.knowledge_collection = self.client.get_or_create_collection(
            name="knowledge",
            embedding_function=_EMBEDDING_FUNCTION,
            metadata={
                "description": "Imported documents and knowledge fragments",
                **hnsw_config,
            },
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

    def search_memories(self, query: str, n_results: int = 5) -> list[VectorSearchResult]:
        """Semantic search for related memories."""
        batch = self.search_memories_batch([query], n_results=n_results)
        return batch[0] if batch else []

    def search_memories_batch(
        self, queries: list[str], n_results: int = 5
    ) -> list[list[VectorSearchResult]]:
        """Batch semantic search — one Chroma round-trip for many queries.

        Returns a list aligned with ``queries``; each entry is the hit list
        for that query.
        """
        if not queries:
            return []
        results = self.memory_collection.query(
            query_texts=queries,
            n_results=n_results,
        )
        return self._parse_search_results(results, len(queries))

    def search_knowledge(self, query: str, n_results: int = 5) -> list[VectorSearchResult]:
        """Semantic search in the knowledge base."""
        batch = self.search_knowledge_batch([query], n_results=n_results)
        return batch[0] if batch else []

    def search_knowledge_batch(
        self, queries: list[str], n_results: int = 5
    ) -> list[list[VectorSearchResult]]:
        """Batch semantic search in knowledge base."""
        if not queries:
            return []
        results = self.knowledge_collection.query(
            query_texts=queries,
            n_results=n_results,
        )
        return self._parse_search_results(results, len(queries))

    def _parse_search_results(self, results: Any, num_queries: int) -> list[list[VectorSearchResult]]:
        """Internal helper to parse ChromaDB QueryResult into list of lists."""
        batches: list[list[VectorSearchResult]] = []

        # Chroma returns None or lists of lists
        ids_by_q = results.get("ids") or []
        docs_by_q = results.get("documents") or []
        metas_by_q = results.get("metadatas") or []
        dists_by_q = results.get("distances") or []

        for q_idx in range(num_queries):
            items: list[VectorSearchResult] = []
            if q_idx < len(ids_by_q) and ids_by_q[q_idx]:
                q_ids = ids_by_q[q_idx]
                q_docs = docs_by_q[q_idx] if docs_by_q and q_idx < len(docs_by_q) else []
                q_metas = metas_by_q[q_idx] if metas_by_q and q_idx < len(metas_by_q) else []
                q_dists = dists_by_q[q_idx] if dists_by_q and q_idx < len(dists_by_q) else []

                for i in range(len(q_ids)):
                    items.append({
                        "id": q_ids[i],
                        "content": q_docs[i] if i < len(q_docs) and q_docs[i] else "",
                        "metadata": q_metas[i] if i < len(q_metas) and q_metas[i] else {},
                        "distance": q_dists[i] if i < len(q_dists) else None,
                    })
            batches.append(items)
        return batches

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

    def index_knowledge_chunk(
        self, content: str, metadata: dict | None = None, chunk_id: str | None = None
    ) -> str:
        """Idempotent knowledge indexing per chunk_id."""
        if chunk_id:
            try:
                self.knowledge_collection.delete(ids=[chunk_id])
            except Exception:
                pass
        return self.add_knowledge_chunk(content, metadata=metadata, chunk_id=chunk_id)

    def delete_memory(self, memory_id: str):
        """Delete a memory by its ID."""
        self.memory_collection.delete(ids=[memory_id])

    def list_memory_ids(self) -> list[str]:
        """Return all memory IDs currently in the vector index."""
        result = self.memory_collection.get(include=[])
        return list(result.get("ids") or [])

    def delete_knowledge_chunks(self, chunk_ids: list[str]):
        """Delete knowledge chunks by their IDs."""
        if chunk_ids:
            self.knowledge_collection.delete(ids=chunk_ids)


from app.core.runtime.runtime_container import _LazyProxy, runtime  # noqa: E402

vector_store = _LazyProxy(lambda: runtime.vector_store)

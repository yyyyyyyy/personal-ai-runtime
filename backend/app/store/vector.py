"""ChromaDB vector store management for semantic search and memory."""

import uuid
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


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

    def search_memories(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search for related memories."""
        results = self.memory_collection.query(
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


vector_store = VectorStore()

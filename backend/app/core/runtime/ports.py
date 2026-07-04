"""Runtime Ports — abstract interfaces the Kernel depends on.

These protocols define the *contract* between Kernel (Domain) and
infrastructure (ChromaDB, LLM providers, tool registries, etc.).
Concrete implementations live in their own modules and are injected
at startup via RuntimeContainer.

Adding a protocol does NOT increase the concept baseline — protocols are
contracts, not new primitives. They formalise what the Kernel already
implicitly depends on.
"""

from __future__ import annotations

from typing import Protocol


class MemoryIndexPort(Protocol):
    """Semantic memory index for storage and recall.

    The Kernel uses this to synchronise memory events with a vector index.
    If None is injected, memory indexing is a no-op (tests, single-node).
    """

    def index_memory(
        self, content: str, metadata: dict | None = None, memory_id: str | None = None
    ) -> str:
        """Index content and return an embedding_id.  Idempotent per memory_id."""
        ...

    def delete_memory(self, memory_id: str) -> None:
        """Remove a memory from the vector index."""
        ...

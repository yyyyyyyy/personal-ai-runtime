"""Vector index double-write atomicity tests.

Validates that removing the pre-compute embedding path eliminates orphan
vectors: if ChromaDB succeeds but the SQLite INSERT were to fail (or
vice-versa), the system never leaves ChromaDB in a state inconsistent
with the durable event log.

Key invariant: ChromaDB is only touched AFTER the SQLite transaction
commits. A ChromaDB failure leaves embedding_id NULL (repaired later)
but never orphans an event.
"""

import pytest

from app.core.runtime.kernel import Kernel  # noqa: E402
from app.core.runtime.kernel.kernel import (  # noqa: E402
    clear_pending_memory_index_repairs,
    get_pending_memory_index_repairs,
)
from app.store.database import Database  # noqa: E402


@pytest.fixture
def kernel(tmp_path):
    clear_pending_memory_index_repairs()
    db = Database(db_path=str(tmp_path / "doublewrite.db"))
    return Kernel(db=db)


class _RecordingIndex:
    """Fake MemoryIndexPort that records all operations."""

    def __init__(self):
        self.store: dict[str, dict] = {}
        self.index_calls = 0
        self.delete_calls = 0

    def index_memory(self, *, content, metadata=None, memory_id=None):
        self.index_calls += 1
        self.store[memory_id] = {"content": content, "metadata": metadata or {}}
        return memory_id

    def delete_memory(self, memory_id):
        self.delete_calls += 1
        self.store.pop(memory_id, None)


class _FailingIndex:
    """Fake MemoryIndexPort whose index_memory always fails."""

    def __init__(self):
        self.delete_calls = 0
        self.index_calls = 0

    def index_memory(self, *, content, metadata=None, memory_id=None):
        self.index_calls += 1
        raise RuntimeError("simulated chroma outage")

    def delete_memory(self, memory_id):
        self.delete_calls += 1


def test_normal_path_backfills_embedding_id(kernel):
    """Happy path: emit MemoryDerived → Chroma indexed → embedding_id backfilled."""
    idx = _RecordingIndex()
    kernel._memory_index = idx

    kernel.emit_event(
        "MemoryDerived", "memory", "m-normal",
        {"category": "fact", "content": "User likes Rust", "confidence": 0.8},
        actor="test",
    )

    # ChromaDB has the memory.
    assert "m-normal" in idx.store
    assert idx.index_calls == 1

    # Projection row exists; embedding_id was backfilled (via MemoryUpdated).
    rows = kernel.query_state("memories", id="m-normal")
    assert len(rows) == 1
    assert rows[0]["embedding_id"] is not None
    assert rows[0]["embedding_id"] == "m-normal"

    clear_pending_memory_index_repairs()


def test_chroma_failure_leaves_no_orphan(kernel):
    """If ChromaDB fails, the event is still durable and NO orphan vector exists."""
    idx = _FailingIndex()
    kernel._memory_index = idx

    kernel.emit_event(
        "MemoryDerived", "memory", "m-fail",
        {"category": "fact", "content": "Survives outage", "confidence": 0.5},
        actor="test",
    )

    # Event is durable despite Chroma failure.
    rows = kernel.query_state("memories", id="m-fail")
    assert len(rows) == 1
    assert rows[0]["content"] == "Survives outage"
    # embedding_id is NULL (will be repaired later).
    assert rows[0]["embedding_id"] is None

    # ChromaDB index_memory was attempted but failed — compensating delete
    # was called to ensure no partial state.
    assert idx.index_calls == 1
    assert idx.delete_calls >= 1, "compensating delete must be called on failure"

    # Repair queue has the pending entry.
    pending = get_pending_memory_index_repairs()
    assert any(p.get("aggregate_id") == "m-fail" for p in pending)

    clear_pending_memory_index_repairs()


def test_no_precompute_before_transaction(kernel):
    """Regression: embedding must NOT be computed before the SQLite INSERT.

    Uses a MemoryDerived event (which WOULD be indexed post-commit) but
    crashes the projector so the transaction rolls back. With post-commit
    indexing, _sync_memory_index is never reached, so index_calls must
    stay constant. Under the old pre-compute path this would have left
    an orphan vector.
    """
    idx = _RecordingIndex()
    kernel._memory_index = idx

    import app.core.runtime.kernel.projectors_registry as pmod

    original = pmod.apply

    def always_fail_memory_derived(event, conn):
        if event.type == "MemoryDerived":
            raise RuntimeError("simulated projector crash before commit")
        original(event, conn)

    pmod.apply = always_fail_memory_derived
    try:
        index_calls_before = idx.index_calls

        # This event crashes in projection → transaction rollback.
        with pytest.raises(RuntimeError, match="projector crash"):
            kernel.emit_event(
                "MemoryDerived", "memory", "m-rollback",
                {"category": "fact", "content": "Should not be indexed", "confidence": 0.5},
                actor="test",
            )

        # DECISIVE assertion: no Chroma write happened for the rolled-back event.
        assert idx.index_calls == index_calls_before, (
            "rolled-back event must not produce a Chroma index call"
        )
        assert "m-rollback" not in idx.store, (
            "rolled-back event must not leave an orphan vector"
        )
        # No repair entry either — the event never committed.
        pending = get_pending_memory_index_repairs()
        assert not any(p.get("aggregate_id") == "m-rollback" for p in pending), (
            "no repair entry for an event that never committed"
        )
    finally:
        pmod.apply = original
        clear_pending_memory_index_repairs()


def test_memory_deleted_syncs_after_commit(kernel):
    """MemoryDeleted removes from Chroma after the event is durable."""
    idx = _RecordingIndex()
    kernel._memory_index = idx

    kernel.emit_event(
        "MemoryDerived", "memory", "m-del",
        {"category": "fact", "content": "To be deleted", "confidence": 0.5},
        actor="test",
    )
    assert "m-del" in idx.store

    kernel.emit_event(
        "MemoryDeleted", "memory", "m-del",
        {"category": "fact"},
        actor="test",
    )
    assert "m-del" not in idx.store

    clear_pending_memory_index_repairs()


def test_memory_updated_without_content_does_not_reindex(kernel):
    """A MemoryUpdated carrying only embedding_id (backfill) must not re-index."""
    idx = _RecordingIndex()
    kernel._memory_index = idx

    # Simulate a backfill event (no content, just embedding_id).
    kernel.emit_event(
        "MemoryUpdated", "memory", "m-backfill",
        {"embedding_id": "pre-existing-id"},
        actor="kernel",
    )

    # No index_memory call because embedding_id is already present.
    assert idx.index_calls == 0

    clear_pending_memory_index_repairs()

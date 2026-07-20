"""Tests for the durable memory index repair queue.

Verifies that:
  1. A failed Chroma index sync lands in memory_index_repairs (durable).
  2. The row survives Kernel restart (in-memory deque does not).
  3. RuntimeLoop._drain_memory_index_repairs succeeds and removes the row.
  4. Exhausting retries marks the row failed_permanent and emits
     MemoryIndexRepairFailed.
"""

import threading

def _fresh_kernel(tmp_path, *, memory_index=None):
    """Build an isolated Kernel against tmp_path with optional memory_index."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "repairs.db"))
    return Kernel(db=db, memory_index=memory_index)


class _BrokenIndex:
    """Memory index stub that always fails to embed."""

    def __init__(self, *, fail_forever=True):
        self.fail_forever = fail_forever
        self.calls = 0

    def index_memory(self, **kwargs):
        self.calls += 1
        if self.fail_forever:
            raise RuntimeError("forced failure")
        return "embed-ok"

    def delete_memory(self, *_args, **_kwargs):
        pass

    def search_memories(self, *_args, **_kwargs):
        return []


class _HealthyIndex:
    """Memory index stub that succeeds on retry."""

    def index_memory(self, **kwargs):
        return "embed-ok"

    def delete_memory(self, *_args, **_kwargs):
        pass

    def search_memories(self, *_args, **_kwargs):
        return []


class _FlakyListingIndex(_HealthyIndex):
    """Fails the first full listing, then exposes a stale vector entry."""

    def __init__(self):
        self.fail_listing = True
        self.ids = {"stale-memory"}

    def list_memory_ids(self):
        if self.fail_listing:
            raise RuntimeError("listing unavailable")
        return list(self.ids)

    def delete_memory(self, memory_id):
        self.ids.discard(memory_id)


class _StatefulIndex(_HealthyIndex):
    def __init__(self, ids=()):
        self.ids = set(ids)

    def list_memory_ids(self):
        return list(self.ids)

    def index_memory(self, *, memory_id, **_kwargs):
        self.ids.add(memory_id)
        return memory_id

    def delete_memory(self, memory_id):
        self.ids.discard(memory_id)


def _count_repairs(db, status=None):
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM memory_index_repairs WHERE status = ?",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM memory_index_repairs").fetchall()
    finally:
        conn.close()
    return list(rows)


def test_failed_index_persists_to_table(tmp_path):
    """A failed Chroma index sync must land in memory_index_repairs."""
    k = _fresh_kernel(tmp_path, memory_index=_BrokenIndex())

    k.emit_event(
        "MemoryDerived", "memory", "m_fail",
        payload={"content": "alpha", "category": "general"},
        actor="test",
    )

    rows = _count_repairs(k._db)
    assert len(rows) == 1, f"expected 1 repair row, got {len(rows)}"
    assert rows[0]["aggregate_id"] == "m_fail"
    assert rows[0]["status"] == "pending"
    assert rows[0]["retry_count"] == 0


def test_repair_row_survives_kernel_restart(tmp_path):
    """The durable row must survive when the in-memory deque is destroyed."""
    db_path = str(tmp_path / "repairs.db")

    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db1 = Database(db_path=db_path)
    k1 = Kernel(db=db1, memory_index=_BrokenIndex())
    k1.emit_event(
        "MemoryDerived", "memory", "m_restart",
        payload={"content": "alpha", "category": "general"},
        actor="test",
    )

    # Drop Kernel + DB; in-memory state is gone.
    del k1
    db1.close()

    # New Database/Kernel pointing at the same file should still see the row.
    db2 = Database(db_path=db_path)
    rows = _count_repairs(db2)
    assert len(rows) == 1
    assert rows[0]["aggregate_id"] == "m_restart"
    db2.close()


def test_drain_repairs_succeeds_and_deletes_row(tmp_path):
    """RuntimeLoop._drain_memory_index_repairs recovers a pending row."""
    from app.core.runtime.kernel import Kernel
    from app.core.runtime.runtime_loop import RuntimeLoop
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "repairs.db"))
    # Stage a failure with a broken index, then swap to a healthy one.
    k = Kernel(db=db, memory_index=_BrokenIndex())
    k.emit_event(
        "MemoryDerived", "memory", "m_recover",
        payload={"content": "alpha", "category": "general"},
        actor="test",
    )
    assert len(_count_repairs(db)) == 1

    # Swap to a healthy index so the worker's retry will succeed.
    k._memory_index = _HealthyIndex()

    loop = RuntimeLoop()
    # Inject the test kernel into loop + kernel_instance (read_ports uses the latter).
    import app.core.runtime.kernel_instance as ki
    import app.core.runtime.runtime_loop as rl_mod
    original_loop_kernel = rl_mod.kernel
    original_instance_kernel = ki.kernel
    rl_mod.kernel = k
    ki.kernel = k
    try:
        loop._drain_memory_index_repairs()
    finally:
        rl_mod.kernel = original_loop_kernel
        ki.kernel = original_instance_kernel

    assert _count_repairs(db) == [], "row should be deleted after successful repair"


def test_full_reconcile_is_retried_after_listing_failure(tmp_path):
    """A transient list failure must not leave stale Chroma IDs permanently."""
    from app.core.runtime.kernel.memory_index_sync import (
        MEMORY_INDEX_RECONCILE_EVENT,
    )
    from app.core.runtime.kernel.sovereignty_ops import (
        _reconcile_memory_index_after_restore,
    )
    from app.core.runtime.runtime_loop import RuntimeLoop

    index = _FlakyListingIndex()
    k = _fresh_kernel(tmp_path, memory_index=index)

    assert _reconcile_memory_index_after_restore(k) is False
    rows = _count_repairs(k._db)
    assert any(row["event_type"] == MEMORY_INDEX_RECONCILE_EVENT for row in rows)

    index.fail_listing = False
    import app.core.runtime.runtime_loop as rl_mod
    original_kernel = rl_mod.kernel
    rl_mod.kernel = k
    try:
        RuntimeLoop()._drain_memory_index_repairs()
    finally:
        rl_mod.kernel = original_kernel

    assert index.ids == set()
    assert _count_repairs(k._db) == []


def test_restore_excludes_old_repair_worker_delete(tmp_path):
    """A queued pre-restore delete cannot run after the restored upsert."""
    import app.core.runtime.runtime_loop as rl_mod
    from app.core.runtime.kernel.memory_index_sync import (
        memory_index_operation_lock,
        persist_memory_index_repair,
    )
    from app.core.runtime.runtime_loop import RuntimeLoop

    k = _fresh_kernel(tmp_path)
    k.emit_event(
        "MemoryDerived",
        "memory",
        "restored-memory",
        payload={"content": "keep me", "category": "general"},
        actor="test",
    )
    rows = k.export_event_log_rows()
    index = _StatefulIndex()
    k._memory_index = index
    persist_memory_index_repair(
        k._db,
        "restored-memory",
        "MemoryDeleted",
        99,
        "old failure",
    )

    original_kernel = rl_mod.kernel
    rl_mod.kernel = k
    worker = threading.Thread(target=RuntimeLoop()._drain_memory_index_repairs)
    try:
        with memory_index_operation_lock:
            worker.start()
            k.import_event_log_rows(rows, rebuild_projections=True)
        worker.join(timeout=5)
    finally:
        rl_mod.kernel = original_kernel

    assert not worker.is_alive()
    assert index.ids == {"restored-memory"}
    assert _count_repairs(k._db) == []


def test_reconcile_deletes_old_vector_for_empty_active_memory(tmp_path):
    from app.core.runtime.kernel.sovereignty_ops import (
        _reconcile_memory_index_after_restore,
    )

    k = _fresh_kernel(tmp_path)
    k.emit_event(
        "MemoryDerived",
        "memory",
        "empty-memory",
        payload={"content": "", "category": "general"},
        actor="test",
    )
    index = _StatefulIndex({"empty-memory"})
    k._memory_index = index

    assert _reconcile_memory_index_after_restore(k) is True
    assert index.ids == set()


def test_drain_repairs_marks_permanent_after_max_retries(tmp_path):
    """After max_retries, the row is marked failed_permanent and an event fires."""
    from app.core.runtime.kernel import Kernel
    from app.core.runtime.runtime_loop import RuntimeLoop
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "repairs.db"))
    k = Kernel(db=db, memory_index=_BrokenIndex(fail_forever=True))
    k.emit_event(
        "MemoryDerived", "memory", "m_permfail",
        payload={"content": "alpha", "category": "general"},
        actor="test",
    )

    loop = RuntimeLoop()
    import app.core.runtime.kernel_instance as ki
    import app.core.runtime.runtime_loop as rl_mod
    original_loop_kernel = rl_mod.kernel
    original_instance_kernel = ki.kernel
    rl_mod.kernel = k
    ki.kernel = k
    try:
        # max_retries in the worker is 5; loop enough times to exhaust.
        for _ in range(6):
            loop._drain_memory_index_repairs()
    finally:
        rl_mod.kernel = original_loop_kernel
        ki.kernel = original_instance_kernel

    rows = _count_repairs(db, status="failed_permanent")
    assert len(rows) == 1, f"expected 1 failed_permanent row, got {len(rows)}"
    assert rows[0]["retry_count"] == 5

    # A MemoryIndexRepairFailed event must be in event_log.
    events = k.read_events(type="MemoryIndexRepairFailed", limit=10)
    assert any(e.aggregate_id == "m_permfail" for e in events), \
        "expected MemoryIndexRepairFailed event in event_log"

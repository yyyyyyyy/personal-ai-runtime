"""Tests for kernel sovereignty export/import."""

import json
import os
import threading

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "sov.db")))


def test_export_import_roundtrip(kernel):
    k = kernel
    k.emit_event("WorkItemCreated", "work_item", "g_exp", payload={'work_type': 'goal', "title": "Export Me"})
    rows = k.export_event_log_rows()
    assert len(rows) >= 1

    k.emit_event("WorkItemDeleted", "work_item", "g_exp", payload={})
    assert not k.query_state("work_items", id="g_exp")

    imported = k.import_event_log_rows(rows, rebuild_projections=True)
    assert imported == len(rows)
    restored = k.query_state("work_items", id="g_exp")
    assert restored and restored[0]["title"] == "Export Me"


def test_table_counts(kernel):
    k = kernel
    k.emit_event("WorkItemCreated", "work_item", "g_cnt", payload={'work_type': 'goal', "title": "Count"})
    counts = k.table_counts(("work_items", "event_log"))
    assert counts["work_items"] >= 1
    assert counts["event_log"] >= 1


def test_export_chat_rows_and_bootstrap(kernel):
    k = kernel
    k.emit_event(
        "ConversationCreated",
        "conversation",
        "c1",
        payload={'work_type': 'goal', "title": "Chat"},
    )
    k.emit_event(
        "MessageAppended",
        "conversation",
        "c1",
        payload={'work_type': 'goal',
            "message_id": "m1",
            "role": "user",
            "content": "hi",
        },
    )
    convs, msgs = k.export_chat_rows()
    assert any(c["id"] == "c1" for c in convs)
    assert any(m["id"] == "m1" for m in msgs)


def test_save_projection_snapshot_and_rebuild(kernel):
    k = kernel
    k.emit_event("WorkItemCreated", "work_item", "g_snap", payload={'work_type': 'goal', "title": "Snap"})
    meta = k.save_projection_snapshot("work_item")
    assert meta["aggregate_type"] == "work_item"
    assert meta["last_applied_seq"] >= 1

    with k._db.get_db() as conn:
        conn.execute("DELETE FROM work_items")

    replayed = k.rebuild("work_item")
    assert replayed >= 0
    assert k.query_state("work_items", id="g_snap")


def test_bootstrap_chat_skips_when_events_present(kernel):
    k = kernel
    k.emit_event("ConversationCreated", "conversation", "c2", payload={'work_type': 'goal', "title": "X"})
    events = k.export_event_log_rows()
    result = k.bootstrap_chat_from_snapshot(
        [{"id": "legacy", "title": "Legacy"}],
        [],
        events,
    )
    assert result == {"conversations": 0, "messages": 0}


def test_export_event_log_batched_matches_full_order(kernel):
    """Batched seq-cursor export must equal a single ordered scan."""
    k = kernel
    for i in range(25):
        k.emit_event(
            "NotificationCreated",
            "notification",
            f"sov_batch_{i}",
            payload={"title": f"t{i}"},
        )
    from app.core.runtime.kernel.query_builder import fetch_event_log_dicts

    with k._db.get_db() as conn:
        batched = fetch_event_log_dicts(conn, batch_size=7)
        full = [dict(r) for r in conn.execute(
            "SELECT * FROM event_log ORDER BY seq ASC"
        ).fetchall()]
    assert [r["seq"] for r in batched] == [r["seq"] for r in full]
    assert [r["id"] for r in batched] == [r["id"] for r in full]


def test_snapshot_point_in_time_and_no_checkpoint_side_effect(kernel, monkeypatch):
    """snapshot() must not write projection checkpoints during export."""
    k = kernel
    k.emit_event(
        "WorkItemCreated",
        "work_item",
        "g_snap_exp",
        payload={"work_type": "goal", "title": "SnapExport"},
    )
    calls: list[object] = []
    monkeypatch.setattr(
        k, "save_projection_snapshots", lambda *a, **kw: calls.append(1) or []
    )
    snap = k.snapshot()
    assert calls == []
    assert snap["format"] == "snapshot"
    assert snap["counts"]["event_log"] == len(snap["event_log"])
    assert snap["counts"]["goals"] >= 1
    assert any(e["aggregate_id"] == "g_snap_exp" for e in snap["event_log"])


def test_streamed_snapshot_excludes_writes_after_first_chunk(kernel):
    """All streamed sections must come from the same SQLite read snapshot."""
    k = kernel
    k.emit_event(
        "NotificationCreated",
        "notification",
        "before-stream",
        payload={"title": "before"},
    )
    chunks = k.iter_snapshot_json_chunks()
    first = next(chunks)

    writer = threading.Thread(
        target=lambda: k.emit_event(
            "NotificationCreated",
            "notification",
            "after-stream-start",
            payload={"title": "after"},
        )
    )
    writer.start()
    writer.join(timeout=5)
    assert not writer.is_alive()

    snapshot = json.loads(first + b"".join(chunks))
    ids = {event["aggregate_id"] for event in snapshot["event_log"]}
    assert "before-stream" in ids
    assert "after-stream-start" not in ids


def test_streamed_snapshot_early_close_does_not_sticky_read(kernel):
    """Closing an export mid-stream must not leave a stale read txn behind."""
    k = kernel
    k.emit_event(
        "NotificationCreated",
        "notification",
        "before-close",
        payload={"title": "before"},
    )
    chunks = k.iter_snapshot_json_chunks()
    next(chunks)
    chunks.close()

    k.emit_event(
        "NotificationCreated",
        "notification",
        "after-close",
        payload={"title": "after"},
    )
    rows = k.export_event_log_rows()
    ids = {row["aggregate_id"] for row in rows}
    assert "after-close" in ids


# ── Atomic restore tests ──────────────────────────────────────────────────


def test_atomic_import_rollback_on_failure(kernel, monkeypatch):
    """Import that fails mid-rebuild must leave the DB in its pre-import state."""
    k = kernel
    # Insert some state BEFORE the import attempt.
    k.emit_event("WorkItemCreated", "work_item", "pre", payload={"work_type": "goal", "title": "PreExisting"})
    assert k.query_state("work_items", id="pre")
    event_count_before = k.count_events("work_item")

    rows = k.export_event_log_rows()
    # Export captures the current state so restore will try to replay it.
    # Force the projection rebuild to fail.
    def _failing_apply(*_args, **_kwargs):
        raise RuntimeError("simulated rebuild failure")
    monkeypatch.setattr(
        "app.core.runtime.kernel.projectors_registry.apply",
        _failing_apply,
    )

    with pytest.raises(RuntimeError, match="simulated rebuild failure"):
        k.import_event_log_rows(rows, rebuild_projections=True)

    # Pre-existing state must still be intact.
    existing = k.query_state("work_items", id="pre")
    assert existing and existing[0]["title"] == "PreExisting"
    assert k.count_events("work_item") == event_count_before


def test_atomic_import_preserves_state_on_partial_failure(kernel, monkeypatch):
    """Count-based invariants hold after a failed import rollback."""
    k = kernel
    for i in range(3):
        k.emit_event("WorkItemCreated", "work_item", f"keep_{i}", payload={"work_type": "goal", "title": f"K{i}"})
    counts_before = k.table_counts(("work_items", "event_log"))

    rows = k.export_event_log_rows()

    # Break the projector such that after clearing tables, applying fails.
    original_apply = __import__(
        "app.core.runtime.kernel.projectors_registry", fromlist=["apply"]
    ).apply
    call_count = [0]

    def _fail_on_second(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 1:
            raise RuntimeError("simulated partial failure")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(
        "app.core.runtime.kernel.projectors_registry.apply",
        _fail_on_second,
    )

    with pytest.raises(RuntimeError, match="simulated partial failure"):
        k.import_event_log_rows(rows, rebuild_projections=True)

    counts_after = k.table_counts(("work_items", "event_log"))
    assert counts_after["work_items"] == counts_before["work_items"]
    assert counts_after["event_log"] == counts_before["event_log"]


def test_atomic_import_no_rebuild_still_succeeds(kernel):
    """import_event_log_rows without rebuild_projections must work atomically."""
    k = kernel
    k.emit_event("WorkItemCreated", "work_item", "no_rb", payload={"work_type": "goal", "title": "NR"})
    rows = k.export_event_log_rows()

    imported = k.import_event_log_rows(rows, rebuild_projections=False)
    assert imported == len(rows)
    # Event log has the rows but projections were not rebuilt — deleted first,
    # so empty.  This is expected when rebuild_projections=False (the caller
    # must call rebuild_all afterwards).  Verify event_log is correct.
    assert k.count_events("work_item") >= len(rows)


def test_import_without_rebuild_clears_old_projection_checkpoints(kernel):
    """Deferred replay must not reuse a checkpoint from the pre-import log."""
    k = kernel
    k.emit_event(
        "WorkItemCreated",
        "work_item",
        "checkpoint-old",
        payload={"work_type": "goal", "title": "Old"},
    )
    k.save_projection_snapshot("work_item")
    rows = k.export_event_log_rows()

    k.import_event_log_rows(rows, rebuild_projections=False)

    with k._db.get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM projection_checkpoints"
        ).fetchone()[0]
    assert count == 0

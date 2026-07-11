"""Tests for kernel sovereignty export/import."""

import os

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

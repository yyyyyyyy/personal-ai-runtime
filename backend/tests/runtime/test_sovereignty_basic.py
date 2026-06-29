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
    k.emit_event("GoalCreated", "goal", "g_exp", payload={"title": "Export Me"})
    rows = k.export_event_log_rows()
    assert len(rows) >= 1

    k.emit_event("GoalDeleted", "goal", "g_exp", payload={})
    assert not k.query_state("goals", id="g_exp")

    imported = k.import_event_log_rows(rows, rebuild_projections=True)
    assert imported == len(rows)
    restored = k.query_state("goals", id="g_exp")
    assert restored and restored[0]["title"] == "Export Me"


def test_table_counts(kernel):
    k = kernel
    k.emit_event("GoalCreated", "goal", "g_cnt", payload={"title": "Count"})
    counts = k.table_counts(("goals", "event_log"))
    assert counts["goals"] >= 1
    assert counts["event_log"] >= 1


def test_export_chat_rows_and_bootstrap(kernel):
    k = kernel
    k.emit_event(
        "ConversationCreated",
        "conversation",
        "c1",
        payload={"title": "Chat"},
    )
    k.emit_event(
        "MessageAppended",
        "conversation",
        "c1",
        payload={
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
    k.emit_event("GoalCreated", "goal", "g_snap", payload={"title": "Snap"})
    meta = k.save_projection_snapshot("goal")
    assert meta["aggregate_type"] == "goal"
    assert meta["last_applied_seq"] >= 1

    with k._db.get_db() as conn:
        conn.execute("DELETE FROM goals")

    replayed = k.rebuild("goal")
    assert replayed >= 0
    assert k.query_state("goals", id="g_snap")


def test_bootstrap_chat_skips_when_events_present(kernel):
    k = kernel
    k.emit_event("ConversationCreated", "conversation", "c2", payload={"title": "X"})
    events = k.export_event_log_rows()
    result = k.bootstrap_chat_from_snapshot(
        [{"id": "legacy", "title": "Legacy"}],
        [],
        events,
    )
    assert result == {"conversations": 0, "messages": 0}

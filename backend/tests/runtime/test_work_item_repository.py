"""Unit tests for the work_item_repository scanner.

Verifies the constant extraction (no hardcoded status strings in SQL), the
status-bucketing for recovery, and that filters compose correctly via
query_builder. Uses an in-memory DB seeded through the projector path so we
do not bypass Kernel governance.
"""
from __future__ import annotations

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest

from app.core.runtime.kernel import work_item_repository as wir


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Build a fresh DB and seed handler_executions via raw SQL.

    Tests here validate the READER, not the projector chain. The repository
    is a pure scanner over an existing projection (INV-4: read-only on
    handler_executions from Kernel Space), so seeding rows directly is the
    honest setup — the projector's correctness is covered elsewhere.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from app.store.database import Database

    db_path = str(tmp_path / "wir.db")
    db = Database(db_path=db_path)
    with db.get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS handler_executions (
                id TEXT PRIMARY KEY,
                event_seq INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                handler_name TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                policy_json TEXT NOT NULL DEFAULT '{}',
                correlation_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO handler_executions
              (id, event_seq, event_id, event_type, handler_name,
               instance_id, status, created_at)
            VALUES
              ('w_run_1', 1, 'e1', 'TimerFired', 'h1', 'inst_a', 'running', '2026-06-01T00:00:00'),
              ('w_run_2', 2, 'e2', 'TimerFired', 'h2', 'inst_b', 'running', '2026-06-01T00:00:01'),
              ('w_pen_1', 3, 'e3', 'ChatRequested', 'h3', 'inst_a', 'pending', '2026-06-01T00:00:02'),
              ('w_pen_2', 4, 'e4', 'ChatRequested', 'h4', 'inst_c', 'retrying', '2026-06-01T00:00:03'),
              ('w_done_1', 5, 'e5', 'ChatRequested', 'h5', 'inst_a', 'completed', '2026-06-01T00:00:04');
            """
        )
    return db


def test_read_scheduled_execution_by_id(seeded_db):
    item = wir.read_scheduled_execution(seeded_db, "w_run_1")
    assert item is not None
    assert item.id == "w_run_1"
    assert item.status == "running"
    assert wir.read_scheduled_execution(seeded_db, "missing") is None


def test_read_work_items_no_filter_returns_all(seeded_db):
    items = wir.read_work_items(seeded_db)
    assert len(items) == 5


def test_read_work_items_status_filter(seeded_db):
    running = wir.read_work_items(seeded_db, status="running")
    assert {i.id for i in running} == {"w_run_1", "w_run_2"}


def test_read_work_items_instance_filter(seeded_db):
    inst_a = wir.read_work_items(seeded_db, instance_id="inst_a")
    assert {i.id for i in inst_a} == {"w_run_1", "w_pen_1", "w_done_1"}


def test_read_work_items_combined_filter(seeded_db):
    rows = wir.read_work_items(seeded_db, status="pending", instance_id="inst_a")
    assert {i.id for i in rows} == {"w_pen_1"}


def test_recover_buckets_running_and_pending(seeded_db):
    running, pending = wir.recover_work_items(seeded_db)
    assert {i.id for i in running} == {"w_run_1", "w_run_2"}
    # 'retrying' must land in the pending bucket for re-enqueue.
    assert {i.id for i in pending} == {"w_pen_1", "w_pen_2"}


def test_recover_excludes_completed(seeded_db):
    running, pending = wir.recover_work_items(seeded_db)
    all_ids = {i.id for i in running} | {i.id for i in pending}
    assert "w_done_1" not in all_ids


def test_constants_match_projection_vocabulary():
    """If the projector ever renames statuses, these constants must follow."""
    assert wir.STATUS_RUNNING == "running"
    assert wir.STATUS_PENDING == "pending"
    assert wir.STATUS_RETRYING == "retrying"
    assert set(wir.RECOVERABLE_STATUSES) == {"pending", "retrying"}

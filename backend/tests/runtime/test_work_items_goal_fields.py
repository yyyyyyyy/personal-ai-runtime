"""Tests for v1.0 Phase 2: WorkItemCreated/Updated projector handles goal fields.

Verifies:
  1. WorkItemCreated with work_type='goal' populates progress/importance/
     urgency/deadline/last_activity_at.
  2. WorkItemCreated with work_type='task' (no goal fields) gets sane
     defaults — byte-identical to pre-v1.0 behavior.
  3. WorkItemUpdated can update goal-specific fields.
  4. rebuild('work_item') preserves all goal fields byte-identical.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "v1_goal_work.db")))


def test_work_item_created_goal_populates_v1_columns(kernel):
    """WorkItemCreated with work_type='goal' populates progress/importance/..."""
    kernel.emit_event(
        "GoalCreated", "goal", "g_v1_1",
        payload={
            "title": "Learn Rust",
            "work_type": "goal",
            "progress": 0.3,
            "importance": 0.9,
            "urgency": 0.6,
            "deadline": "2026-12-31T00:00:00Z",
            "last_activity_at": "2026-07-05T00:00:00Z",
        },
        actor="test",
    )
    rows = kernel.query_state("work_items", id="g_v1_1")
    assert len(rows) == 1
    row = rows[0]
    assert row["work_type"] == "goal"
    assert row["progress"] == 0.3
    assert row["importance"] == 0.9
    assert row["urgency"] == 0.6
    assert row["deadline"] == "2026-12-31T00:00:00Z"
    assert row["last_activity_at"] == "2026-07-05T00:00:00Z"


def test_work_item_created_task_uses_defaults(kernel):
    """WorkItemCreated with work_type='task' gets schema defaults for v1 columns."""
    kernel.emit_event(
        "GoalCreated", "goal", "t_v1_1",
        payload={"title": "Ship feature", "work_type": "task"},
        actor="test",
    )
    rows = kernel.query_state("work_items", id="t_v1_1")
    assert len(rows) == 1
    row = rows[0]
    assert row["work_type"] == "task"
    # Defaults from schema_ddl.py WORK_ITEMS_SCHEMA
    assert row["progress"] == 0
    assert row["importance"] == 0.5
    assert row["urgency"] == 0.5
    assert row["deadline"] is None
    assert row["last_activity_at"] is None


def test_work_item_updated_changes_goal_fields(kernel):
    """WorkItemUpdated can update progress/importance/urgency/deadline."""
    kernel.emit_event(
        "GoalCreated", "goal", "g_v1_2",
        payload={
            "title": "Write book",
            "work_type": "goal",
            "progress": 0.0,
            "importance": 0.8,
        },
        actor="test",
    )
    kernel.emit_event(
        "WorkItemUpdated", "work_item", "g_v1_2",
        payload={
            "progress": 0.5,
            "urgency": 0.7,
            "deadline": "2026-11-01T00:00:00Z",
            "last_activity_at": "2026-07-06T00:00:00Z",
        },
        actor="test",
    )
    rows = kernel.query_state("work_items", id="g_v1_2")
    row = rows[0]
    assert row["progress"] == 0.5
    assert row["urgency"] == 0.7
    assert row["deadline"] == "2026-11-01T00:00:00Z"
    assert row["last_activity_at"] == "2026-07-06T00:00:00Z"
    # Unspecified fields retain original values
    assert row["importance"] == 0.8


def test_rebuild_preserves_goal_fields_byte_identical(kernel):
    """rebuild('work_item') must reproduce goal fields exactly."""
    kernel.emit_event(
        "GoalCreated", "goal", "g_v1_3",
        payload={
            "title": "Run marathon",
            "work_type": "goal",
            "progress": 0.65,
            "importance": 0.95,
            "urgency": 0.4,
            "deadline": "2026-10-15T00:00:00Z",
            "last_activity_at": "2026-07-04T12:00:00Z",
        },
        actor="test",
    )
    kernel.emit_event(
        "WorkItemUpdated", "work_item", "g_v1_3",
        payload={"progress": 0.75, "last_activity_at": "2026-07-05T12:00:00Z"},
        actor="test",
    )

    before = kernel.query_state("work_items", id="g_v1_3")[0]
    kernel.rebuild("work_item")
    after = kernel.query_state("work_items", id="g_v1_3")[0]

    assert dict(before) == dict(after), (
        f"rebuild drift: before={dict(before)} after={dict(after)}"
    )


def test_legacy_work_item_created_without_goal_fields_still_works(kernel):
    """A WorkItemCreated event emitted by pre-v1.0 code paths (no goal fields
    in payload) must still project cleanly — projector's .get(field, default)
    falls back to schema defaults.
    """
    kernel.emit_event(
        "GoalCreated", "goal", "legacy_1",
        payload={"title": "Legacy task", "work_type": "task"},
        actor="test",
    )
    rows = kernel.query_state("work_items", id="legacy_1")
    assert rows[0]["title"] == "Legacy task"
    assert rows[0]["progress"] == 0
    assert rows[0]["importance"] == 0.5

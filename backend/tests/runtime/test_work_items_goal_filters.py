"""Tests for v1.0 Phase 3b: _query_work_items supports goal-style filters."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest


@pytest.fixture
def kernel_with_goal_work_items(tmp_path):
    """Seed work_items with goal rows for filter testing."""
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "work_items_goals.db")))

    # Active high-importance goal with deadline
    k.emit_event("WorkItemCreated", "work_item", "g_active_1", payload={
        "title": "Important active goal",
        "work_type": "goal", "status": "active",
        "importance": 0.9, "urgency": 0.3,
        "deadline": "2026-12-01T00:00:00Z",
        "last_activity_at": "2026-06-01T00:00:00Z",
    })
    # Active lower-importance goal, no deadline
    k.emit_event("WorkItemCreated", "work_item", "g_active_2", payload={
        "title": "Less urgent goal",
        "work_type": "goal", "status": "active",
        "importance": 0.5, "urgency": 0.5,
        "last_activity_at": "2026-07-04T00:00:00Z",
    })
    # Completed goal
    k.emit_event("WorkItemCreated", "work_item", "g_done_1", payload={
        "title": "Done", "work_type": "goal", "status": "completed",
        "importance": 0.5,
    })
    # A regular task (must be excluded when work_type='goal')
    k.emit_event("WorkItemCreated", "work_item", "t_task_1", payload={
        "title": "Plain task", "work_type": "task", "status": "pending",
    })

    return k


def test_status_in_filter(kernel_with_goal_work_items):
    """status_in matches multiple statuses, excludes others."""
    k = kernel_with_goal_work_items
    rows = k.query_state(
        "work_items", work_type="goal",
        status_in=("active", "in_progress"), limit=50,
    )
    statuses = {r["status"] for r in rows}
    assert statuses == {"active"}, f"got {statuses}"
    assert all(r["id"].startswith("g_active") for r in rows)


def test_last_activity_older_than_days(kernel_with_goal_work_items):
    """last_activity_older_than_days excludes recently-touched rows."""
    k = kernel_with_goal_work_items
    # g_active_1 (Jun 1) is >3 days old; g_active_2 (Jul 4) is recent.
    rows = k.query_state(
        "work_items", work_type="goal", status="active",
        last_activity_older_than_days=3, limit=50,
    )
    ids = {r["id"] for r in rows}
    assert "g_active_1" in ids
    assert "g_active_2" not in ids


def test_has_deadline_filter(kernel_with_goal_work_items):
    """has_deadline excludes rows without deadline."""
    k = kernel_with_goal_work_items
    rows = k.query_state(
        "work_items", work_type="goal", has_deadline=True, limit=50,
    )
    ids = {r["id"] for r in rows}
    assert "g_active_1" in ids
    # g_active_2 has no deadline
    assert "g_active_2" not in ids


def test_importance_desc_order(kernel_with_goal_work_items):
    """importance_desc orders highest-importance first."""
    k = kernel_with_goal_work_items
    rows = k.query_state(
        "work_items", work_type="goal", status="active",
        order="importance_desc", limit=10,
    )
    assert rows[0]["id"] == "g_active_1"  # importance=0.9
    assert rows[1]["id"] == "g_active_2"  # importance=0.5


def test_importance_urgency_desc_order(kernel_with_goal_work_items):
    """importance_urgency_desc orders by combined score."""
    k = kernel_with_goal_work_items
    rows = k.query_state(
        "work_items", work_type="goal", status="active",
        order="importance_urgency_desc", limit=10,
    )
    # g_active_1: 0.9 importance (decisive); g_active_2: 0.5 importance
    assert rows[0]["id"] == "g_active_1"


def test_last_activity_asc_order(kernel_with_goal_work_items):
    """last_activity_asc orders oldest activity first."""
    k = kernel_with_goal_work_items
    rows = k.query_state(
        "work_items", work_type="goal", status="active",
        order="last_activity_asc", limit=10,
    )
    # g_active_1 (Jun 1) before g_active_2 (Jul 4)
    assert rows[0]["id"] == "g_active_1"


def test_work_type_filter_excludes_tasks(kernel_with_goal_work_items):
    """work_type='goal' excludes task rows."""
    k = kernel_with_goal_work_items
    rows = k.query_state("goals", limit=50)
    ids = {r["id"] for r in rows}
    assert "t_task_1" not in ids
    assert "g_active_1" in ids


def test_legacy_task_orders_still_work(kernel_with_goal_work_items):
    """Existing task-side orders (priority_desc, created_at_desc) unchanged."""
    k = kernel_with_goal_work_items
    # No work_type filter — all rows
    rows = k.query_state("work_items", order="created_at_desc", limit=10)
    assert len(rows) >= 4

    rows = k.query_state("work_items", order="priority_desc", limit=10)
    assert len(rows) >= 4

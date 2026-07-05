"""Tests for v1.0 Phase 3c: parent goal progress auto-recalculation in projector.

The WorkItemStatusChanged projector now derives parent goal progress as
completed_children / total_children. This is pure projection (no event
emission) so rebuild produces byte-identical state.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "v1_progress.db")))


def test_child_completion_recalculates_parent_progress(kernel):
    """Completing a child updates the parent goal's progress in the same
    transaction, no extra events needed."""
    # Parent goal
    kernel.emit_event("GoalCreated", "goal", "goal_p1", payload={
        "title": "Parent goal", "work_type": "goal", "progress": 0.0,
    })
    # Two child tasks
    kernel.emit_event("GoalCreated", "goal", "task_c1", payload={
        "title": "Child 1", "work_type": "task", "parent_work_id": "goal_p1",
    })
    kernel.emit_event("GoalCreated", "goal", "task_c2", payload={
        "title": "Child 2", "work_type": "task", "parent_work_id": "goal_p1",
    })

    # Complete one child → progress should become 0.5
    kernel.emit_event(
        "WorkItemStatusChanged", "work_item", "task_c1",
        payload={"status": "completed"},
    )
    parent = kernel.query_state("work_items", id="goal_p1")[0]
    assert parent["progress"] == 0.5

    # Complete the other → progress should become 1.0
    kernel.emit_event(
        "WorkItemStatusChanged", "work_item", "task_c2",
        payload={"status": "completed"},
    )
    parent = kernel.query_state("work_items", id="goal_p1")[0]
    assert parent["progress"] == 1.0


def test_progress_recalculation_ignores_non_goal_parents(kernel):
    """A task's status change does not affect a parent that is itself a task."""
    # Parent task (not goal)
    kernel.emit_event("GoalCreated", "goal", "task_parent", payload={
        "title": "Parent task", "work_type": "task", "parent_work_id": None,
    })
    kernel.emit_event("GoalCreated", "goal", "task_sub", payload={
        "title": "Sub", "work_type": "task", "parent_work_id": "task_parent",
    })

    kernel.emit_event(
        "WorkItemStatusChanged", "work_item", "task_sub",
        payload={"status": "completed"},
    )
    parent = kernel.query_state("work_items", id="task_parent")[0]
    # Parent task's progress should remain at default (0)
    assert parent["progress"] == 0


def test_progress_recalculation_byte_identical_after_rebuild(kernel):
    """rebuild('work_item') must produce the same progress value."""
    kernel.emit_event("GoalCreated", "goal", "goal_rb", payload={
        "title": "Rebuild goal", "work_type": "goal", "progress": 0.0,
    })
    for i in range(3):
        kernel.emit_event("GoalCreated", "goal", f"task_rb_{i}", payload={
            "title": f"Task {i}", "work_type": "task", "parent_work_id": "goal_rb",
        })
    # Complete 2 of 3
    kernel.emit_event("WorkItemStatusChanged", "work_item", "task_rb_0",
                      payload={"status": "completed"})
    kernel.emit_event("WorkItemStatusChanged", "work_item", "task_rb_1",
                      payload={"status": "completed"})

    before = kernel.query_state("work_items", id="goal_rb")[0]
    assert before["progress"] == 2 / 3

    kernel.rebuild("work_item")
    after = kernel.query_state("work_items", id="goal_rb")[0]
    assert dict(before) == dict(after), (
        f"rebuild drift: before={dict(before)} after={dict(after)}"
    )


def test_progress_supports_legacy_parent_goal_id(kernel):
    """Children linked via parent_goal_id (legacy) also count toward goal progress."""
    kernel.emit_event("GoalCreated", "goal", "goal_legacy", payload={
        "title": "Legacy-linked goal", "work_type": "goal", "progress": 0.0,
    })
    # Child with parent_goal_id (legacy pattern, e.g. /api/goals/{id}/actions)
    kernel.emit_event("GoalCreated", "goal", "task_legacy_1", payload={
        "title": "Legacy child", "work_type": "task",
        "parent_goal_id": "goal_legacy",
    })

    kernel.emit_event("WorkItemStatusChanged", "work_item", "task_legacy_1",
                      payload={"status": "completed"})
    parent = kernel.query_state("work_items", id="goal_legacy")[0]
    assert parent["progress"] == 1.0


def test_no_children_progress_unchanged(kernel):
    """A goal with no children keeps its existing progress on status changes
    of unrelated work items."""
    kernel.emit_event("GoalCreated", "goal", "goal_solo", payload={
        "title": "Solo goal", "work_type": "goal", "progress": 0.3,
    })
    # An unrelated task
    kernel.emit_event("GoalCreated", "goal", "task_other", payload={
        "title": "Other", "work_type": "task",
    })
    kernel.emit_event("WorkItemStatusChanged", "work_item", "task_other",
                      payload={"status": "completed"})

    parent = kernel.query_state("work_items", id="goal_solo")[0]
    assert parent["progress"] == 0.3  # unchanged

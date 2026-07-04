"""Actions event-sourcing: create, update, delete, rebuild consistency."""

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "actions_test.db"))
    return Kernel(db=db)


class TestActionsEventSourced:
    def test_actions_crud_and_rebuild(self, kernel):
        k = kernel
        k.emit_event("GoalCreated", "goal", "g1", {"title": "Test Goal"}, actor="user")

        k.emit_event(
            "WorkItemCreated", "work_item", "a1",
            {"parent_goal_id": "g1", "title": "Step 1", "status": "pending", "work_type": "action"},
            actor="user",
        )
        k.emit_event(
            "WorkItemCreated", "work_item", "a2",
            {"parent_goal_id": "g1", "title": "Step 2", "status": "pending", "work_type": "action"},
            actor="user",
        )
        k.emit_event(
            "WorkItemUpdated", "work_item", "a1",
            {"status": "completed", "completed_at": "2026-01-01T00:00:00"},
            actor="user",
        )
        k.emit_event("WorkItemDeleted", "work_item", "a2", actor="user")

        before = k.query_state("work_items", parent_goal_id="g1", work_type="action")
        assert len(before) == 1
        assert before[0]["status"] == "completed"

        count = k.rebuild("work_item")
        assert count >= 4
        after = k.query_state("work_items", parent_goal_id="g1", work_type="action")
        assert before == after

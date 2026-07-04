"""W2 tests for kernel.query_state goal/action filter extensions."""

import os

os.environ["LLM_API_KEY"] = "test-key"

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def _kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "query_state_w2.db")))


class TestQueryStateW2:
    def test_goals_stagnant_and_deadline_filters(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event(
            "GoalCreated",
            "goal",
            "g-stale",
            payload={"title": "Stale", "status": "active"},
        )
        k.emit_event(
            "GoalUpdated",
            "goal",
            "g-stale",
            payload={"last_activity_at": "2020-01-01T00:00:00"},
        )
        k.emit_event(
            "GoalCreated",
            "goal",
            "g-due",
            payload={
                "title": "Due",
                "status": "active",
                "deadline": "2099-12-31T00:00:00",
            },
        )

        stale = k.query_state("goals", status="active", last_activity_older_than_days=3, limit=50)
        assert {g["id"] for g in stale} == {"g-stale"}

        due = k.query_state("goals", status="active", deadline_within_days=36500, limit=50)
        assert {g["id"] for g in due} == {"g-due"}

    def test_actions_status_filter(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "g1", payload={"title": "G"})
        k.emit_event(
            "WorkItemCreated",
            "work_item",
            "a1",
            payload={"parent_goal_id": "g1", "title": "Pending", "status": "pending", "work_type": "action"},
        )
        k.emit_event(
            "WorkItemCreated",
            "work_item",
            "a2",
            payload={"parent_goal_id": "g1", "title": "Done", "status": "done", "work_type": "action"},
        )

        pending = k.query_state("work_items", status="pending", limit=10)
        assert len(pending) == 1
        assert pending[0]["id"] == "a1"

    def test_tasks_depends_on_filter(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "g1", payload={"title": "G"})
        k.emit_event("WorkItemCreated", "work_item", "t1", payload={"title": "Dep"})
        k.emit_event(
            "WorkItemCreated",
            "work_item",
            "t2",
            payload={"title": "Blocked", "dependencies_json": '["t1"]'},
        )

        blocked = k.query_state("work_items", status="pending", depends_on_task="t1")
        assert len(blocked) == 1
        assert blocked[0]["id"] == "t2"

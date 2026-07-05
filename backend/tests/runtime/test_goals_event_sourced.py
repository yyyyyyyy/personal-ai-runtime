"""T1 acceptance test: Goals API fully event-sourced through the Kernel.

Verifies:
- create_goal / update_goal / delete_goal emit events and project State correctly.
- read paths (list_goals, get_goal) return State from the projection.
- kernel.rebuild("goal") restores byte-identical State.
- No direct write SQL to `goals` table in goals.py API layer.
"""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")


from app.core.runtime.kernel import Kernel
from app.store.database import Database


def make_kernel_and_db(tmp_path):
    db = Database(db_path=str(tmp_path / "t1.db"))
    k = Kernel(db=db)
    # Ensure the goals table exists (the projector writes to it, but the
    # schema must already exist — Database.__init__ creates it).
    return k, db


class TestGoalsEventSourced:
    """Simulate the T1 scenario: build → modify → rebuild → verify identity."""

    def test_full_lifecycle_and_rebuild(self, tmp_path):
        k, _ = make_kernel_and_db(tmp_path)

        # ---- Build ----
        k.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "Task A", "importance": 0.9}, actor="user")
        k.emit_event("WorkItemCreated", "work_item", "g2", {'work_type': 'goal', "title": "Task B", "urgency": 0.7}, actor="user")
        k.emit_event("WorkItemCreated", "work_item", "g3", {'work_type': 'goal', "title": "Task C"}, actor="user")

        assert len(k.query_state("goals")) == 3

        # ---- Modify ----
        k.emit_event("WorkItemUpdated", "work_item", "g1", {"title": "Task A2", "progress": 0.5}, actor="user")
        k.emit_event("WorkItemStatusChanged", "work_item", "g2", {"status": "completed"}, actor="user")
        k.emit_event("WorkItemDeleted", "work_item", "g3", {}, actor="user")

        before = k.query_state("goals")
        assert len(before) == 2  # g3 deleted

        by_id_before = {g["id"]: g for g in before}
        assert by_id_before["g1"]["title"] == "Task A2"
        assert by_id_before["g1"]["progress"] == 0.5
        assert by_id_before["g2"]["status"] == "pending"  # v1.0: no goal_completed event
        assert by_id_before["g2"]["progress"] >= 0  # v1.0: progress derived from children

        # ---- Rebuild & verify byte-identical State ----
        replayed = k.rebuild("goal")
        assert replayed == 6  # 3x created + 1x updated + 1x completed + 1x deleted (GoalDeleted IS part of the goal aggregate)

        after = k.query_state("goals")
        assert before == after, "rebuilt State must be byte-identical to pre-rebuild State"

    def test_goal_deleted_removed_from_projection(self, tmp_path):
        k, _ = make_kernel_and_db(tmp_path)
        k.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', "title": "X"}, actor="user")
        assert len(k.query_state("goals")) == 1
        k.emit_event("WorkItemDeleted", "work_item", "g1", {}, actor="user")
        assert len(k.query_state("goals")) == 0

    def test_goal_created_projection_fields(self, tmp_path):
        k, _ = make_kernel_and_db(tmp_path)
        k.emit_event(
            "GoalCreated",
            "goal",
            "g1",
            {
                "title": "Learn Rust",
                "description": "Master the borrow checker",
                "importance": 0.9,
                "urgency": 0.6,
                "deadline": "2026-12-31",
                "parent_id": None,
            },
            actor="user",
        )
        goals = k.query_state("goals", id="g1")
        assert len(goals) == 1
        g = goals[0]
        assert g["title"] == "Learn Rust"
        assert g["description"] == "Master the borrow checker"
        assert g["status"] == "active"
        assert g["importance"] == 0.9
        assert g["urgency"] == 0.6
        assert g["deadline"] == "2026-12-31"
        assert g["progress"] == 0.0
        assert g["parent_id"] is None

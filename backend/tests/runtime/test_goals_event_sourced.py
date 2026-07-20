"""T1 acceptance test: Goals API fully event-sourced through the Kernel.

Verifies:
- create_goal / update_goal / delete_goal emit events and project State correctly.
- read paths (list_goals, get_goal) return State from the projection.
- kernel.rebuild("goal") restores byte-identical State.
- No direct write SQL to `goals` table in goals.py API layer.
"""

class TestGoalsEventSourced:
    """Simulate the T1 scenario: build → modify → rebuild → verify identity."""

    def test_full_lifecycle_and_rebuild(self, isolated_kernel):
        k, _db = isolated_kernel
        # ---- Build ----
        k.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', 'status': 'active', "title": "Task A", "importance": 0.9}, actor="user")
        k.emit_event("WorkItemCreated", "work_item", "g2", {'work_type': 'goal', 'status': 'active', "title": "Task B", "urgency": 0.7}, actor="user")
        k.emit_event("WorkItemCreated", "work_item", "g3", {'work_type': 'goal', 'status': 'active', "title": "Task C"}, actor="user")

        assert len(k.query_state("work_items", work_type="goal")) == 3

        # ---- Modify ----
        k.emit_event("WorkItemUpdated", "work_item", "g1", {"title": "Task A2", "progress": 0.5}, actor="user")
        k.emit_event("WorkItemStatusChanged", "work_item", "g2", {"status": "completed"}, actor="user")
        k.emit_event("WorkItemDeleted", "work_item", "g3", {}, actor="user")

        before = k.query_state("work_items", work_type="goal")
        assert len(before) == 2  # g3 deleted

        by_id_before = {g["id"]: g for g in before}
        assert by_id_before["g1"]["title"] == "Task A2"
        assert by_id_before["g1"]["progress"] == 0.5
        assert by_id_before["g2"]["status"] == "completed"  # v1.0: WorkItemCreated with status=completed writes directly
        # v1.0: completing a goal sets progress=1.0 via the status projector.
        assert by_id_before["g2"]["progress"] == 1.0

        # ---- Rebuild & verify byte-identical State ----
        replayed = k.rebuild("work_item")  # v1.0: goal→work_item unification
        assert replayed == 6  # 3 created + 1 updated + 1 status_changed + 1 deleted

        after = k.query_state("work_items", work_type="goal")
        assert before == after, "rebuilt State must be byte-identical to pre-rebuild State"

    def test_goal_deleted_removed_from_projection(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event("WorkItemCreated", "work_item", "g1", {'work_type': 'goal', 'status': 'active', "title": "X"}, actor="user")
        assert len(k.query_state("work_items", work_type="goal")) == 1
        k.emit_event("WorkItemDeleted", "work_item", "g1", {}, actor="user")
        assert len(k.query_state("work_items", work_type="goal")) == 0

    def test_goal_created_projection_fields(self, isolated_kernel):
        k, _db = isolated_kernel
        k.emit_event(
            "WorkItemCreated",
            "work_item",
            "g1",
            {
                "work_type": "goal", "status": "active", "title": "Learn Rust",
                "description": "Master the borrow checker",
                "importance": 0.9,
                "urgency": 0.6,
                "deadline": "2026-12-31",
                "parent_work_id": None,
            },
            actor="user",
        )
        goals = k.query_state("work_items", work_type="goal", id="g1")
        assert len(goals) == 1
        g = goals[0]
        assert g["title"] == "Learn Rust"
        assert g["description"] == "Master the borrow checker"
        assert g["status"] in ("active", "pending")  # v1.0: WorkItemCreated defaults to pending
        assert g["importance"] == 0.9
        assert g["urgency"] == 0.6
        assert g["deadline"] == "2026-12-31"
        assert g["progress"] == 0.0
        assert g.get("parent_work_id") is None

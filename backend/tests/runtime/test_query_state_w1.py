"""W1 tests for kernel.query_state filter extensions."""

import os

os.environ["LLM_API_KEY"] = "test-key"

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def _kernel(tmp_path):
    return Kernel(db=Database(db_path=str(tmp_path / "query_state_w1.db")))


class TestQueryStateW1:
    def test_tasks_by_id_and_parent(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("GoalCreated", "goal", "g1", payload={"title": "Goal"})
        k.emit_event(
            "TaskCreated",
            "task",
            "t-root",
            payload={"name": "Root", "parent_goal_id": "g1", "parent_task_id": None},
        )
        k.emit_event(
            "TaskCreated",
            "task",
            "t-child",
            payload={"name": "Child", "parent_goal_id": "g1", "parent_task_id": "t-root", "priority": 5},
        )

        assert k.query_state("tasks", id="t-root")[0]["name"] == "Root"
        subs = k.query_state("tasks", parent_task_id="t-root", order="priority_desc")
        assert len(subs) == 1
        assert subs[0]["name"] == "Child"

        roots = k.query_state("tasks", parent_goal_id="g1", root_only=True, order="priority_desc")
        assert len(roots) == 1
        assert roots[0]["id"] == "t-root"

    def test_tasks_status_and_limit(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event("TaskCreated", "task", "t1", payload={"name": "A", "priority": 1})
        k.emit_event("TaskCreated", "task", "t2", payload={"name": "B", "priority": 2})
        k.emit_event("TaskStatusChanged", "task", "t1", payload={"status": "running"}, actor="user")

        running = k.query_state("tasks", status="running", limit=10, order="priority_desc_created_desc")
        assert len(running) == 1
        assert running[0]["id"] == "t1"

    def test_approvals_by_status(self, tmp_path):
        k = _kernel(tmp_path)
        k.emit_event(
            "ApprovalRequested",
            "approval",
            "a1",
            payload={"action": "write_file", "risk": "high", "ctx": {}},
        )
        k.emit_event(
            "ApprovalRequested",
            "approval",
            "a2",
            payload={"action": "shell_exec", "risk": "high", "ctx": {}},
        )
        k.emit_event(
            "ApprovalGranted",
            "approval",
            "a2",
            payload={"action": "shell_exec", "reason": "ok"},
        )

        pending = k.query_state("approvals", status="pending")
        assert len(pending) == 1
        assert pending[0]["id"] == "a1"

        one = k.query_state("approvals", id="a2")
        assert one[0]["status"] == "approved"

    def test_memories_decay_filters(self, tmp_path, monkeypatch):
        # query_state filter test — SQL projection only; skip Chroma index sync.
        monkeypatch.setattr(Kernel, "_sync_memory_index", lambda self, event: None)
        k = _kernel(tmp_path)
        k.emit_event(
            "MemoryDerived",
            "memory",
            "m1",
            payload={"content": "low", "confidence": 0.25, "category": "fact"},
        )
        k.emit_event(
            "MemoryDerived",
            "memory",
            "m2",
            payload={"content": "mid", "confidence": 0.5, "category": "fact"},
        )
        k.emit_event(
            "MemoryDerived",
            "memory",
            "m3",
            payload={"content": "high", "confidence": 0.9, "category": "fact"},
        )

        candidates = k.query_state(
            "memories",
            confidence_gt=0.1,
            confidence_lt=0.8,
            decay_eligible=True,
            limit=50,
        )
        ids = {m["id"] for m in candidates}
        assert ids == {"m1", "m2"}

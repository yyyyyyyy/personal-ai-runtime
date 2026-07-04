"""T5 acceptance test: Task lifecycle events + dynamic agent spawn with trace.
ADR-0007 Step 10: uses direct emit_event instead of deleted create_task/spawn_agent/kill_agent.
"""

import os
import uuid

os.environ.setdefault("LLM_API_KEY", "test-key")


from app.core.runtime.kernel import Kernel
from app.store.database import Database


def make_kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "t5.db"))
    return Kernel(db=db), db


class TestTaskAgent:
    def test_full_task_agent_lifecycle_and_rebuild(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        cid = "plan_weekly_report"
        task_id = f"task_{uuid.uuid4().hex}"
        agent_id = f"agent_{uuid.uuid4().hex}"

        # 1. Create task (ADR-0007 Step 10: emit event directly)
        k.emit_event(
            type="WorkItemCreated", aggregate_type="work_item", aggregate_id=task_id,
            payload={"title": "Plan weekly report", "description": "Generate weekly report for the team"},
            actor="user", correlation_id=cid,
        )
        tasks = k.query_state("work_items")
        assert any(tk["id"] == task_id and tk["status"] == "pending" for tk in tasks)

        # 2. Spawn agent (emit TaskStarted + AgentSpawned)
        k.emit_event("WorkItemStarted", "work_item", task_id,
                     payload={"agent_id": agent_id, "spec": "planner"}, actor="kernel", correlation_id=cid)
        k.emit_event("AgentSpawned", "work_item", agent_id,
                     payload={"spec": "planner", "task_ref": task_id}, actor="kernel", correlation_id=cid)

        tasks = k.query_state("work_items")
        assert any(tk["id"] == task_id and tk["status"] == "running" for tk in tasks)

        # 3. Kill agent (emit AgentTerminated + TaskCompleted)
        k.emit_event("AgentTerminated", "work_item", agent_id,
                     payload={"task_ref": task_id, "result": {"status": "success", "output": "Weekly report planned with 5 steps"}},
                     actor="kernel", correlation_id=cid)
        k.emit_event("WorkItemCompleted", "work_item", task_id,
                     payload={"status": "success", "output": "Weekly report planned with 5 steps"},
                     actor="kernel", correlation_id=cid)

        tasks = k.query_state("work_items")
        assert any(tk["id"] == task_id and tk["status"] == "completed" for tk in tasks)

        # 4. Full trace
        trace = k.read_events(correlation_id=cid)
        trace_types = [e.type for e in trace]
        assert "WorkItemCreated" in trace_types
        assert "WorkItemStarted" in trace_types
        assert "AgentSpawned" in trace_types
        assert "AgentTerminated" in trace_types
        assert "WorkItemCompleted" in trace_types

        # 5. Rebuild
        k.rebuild("work_item")
        tasks2 = k.query_state("work_items")
        assert any(tk["id"] == task_id and tk["status"] == "completed" for tk in tasks2)

    def test_agent_is_ephemeral(self, tmp_path):
        """Agents leave no persistent state — only events."""
        k, _ = make_kernel(tmp_path)
        cid = "ephem_test"
        task_id = f"task_{uuid.uuid4().hex}"
        agent_id = f"agent_{uuid.uuid4().hex}"

        k.emit_event("WorkItemCreated", "work_item", task_id, payload={"title": "Test ephemeral"}, actor="test", correlation_id=cid)
        k.emit_event("WorkItemStarted", "work_item", task_id, payload={"agent_id": agent_id, "spec": "brain"}, actor="kernel", correlation_id=cid)
        k.emit_event("AgentSpawned", "work_item", agent_id, payload={"spec": "brain", "task_ref": task_id}, actor="kernel", correlation_id=cid)
        k.emit_event("AgentTerminated", "work_item", agent_id, payload={"task_ref": task_id}, actor="kernel", correlation_id=cid)
        k.emit_event("WorkItemCompleted", "work_item", task_id, payload={}, actor="kernel", correlation_id=cid)

        trace = k.read_events(correlation_id=cid)
        event_types = [e.type for e in trace]
        assert event_types.count("AgentSpawned") == 1
        assert event_types.count("AgentTerminated") == 1

    def test_task_failed_on_error(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        cid = "fail_test"
        task_id = f"task_{uuid.uuid4().hex}"
        agent_id = f"agent_{uuid.uuid4().hex}"

        k.emit_event("WorkItemCreated", "work_item", task_id, payload={"title": "Failing task"}, actor="test", correlation_id=cid)
        k.emit_event("WorkItemStarted", "work_item", task_id, payload={"agent_id": agent_id, "spec": "planner"}, actor="kernel", correlation_id=cid)
        k.emit_event("AgentSpawned", "work_item", agent_id, payload={"spec": "planner", "task_ref": task_id}, actor="kernel", correlation_id=cid)
        k.emit_event("AgentTerminated", "work_item", agent_id,
                     payload={"task_ref": task_id, "result": {"status": "error", "error": "Planner crashed"}},
                     actor="kernel", correlation_id=cid)
        k.emit_event("WorkItemFailed", "work_item", task_id,
                     payload={"status": "error", "error": "Planner crashed"}, actor="kernel", correlation_id=cid)

        tasks = k.query_state("work_items")
        assert any(tk["id"] == task_id and tk["status"] == "failed" for tk in tasks)

        trace = k.read_events(correlation_id=cid)
        trace_types = [e.type for e in trace]
        assert "WorkItemFailed" in trace_types
        assert "WorkItemCompleted" not in trace_types

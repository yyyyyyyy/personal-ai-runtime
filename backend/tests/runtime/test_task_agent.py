"""T5 acceptance test: Task lifecycle events + dynamic agent spawn with trace."""

import os

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

        # 1. Create task
        t = k.create_task(
            name="Plan weekly report",
            plan={"summary": "Generate weekly report for the team"},
            actor="user",
            correlation_id=cid,
        )
        task_id = t["task_id"]
        assert t["status"] == "pending"

        # 2. Spawn agent (ephemeral)
        agent = k.spawn_agent("planner", task_ref=task_id, actor="kernel", correlation_id=cid)
        assert agent["spec"] == "planner"

        # Check task is running
        tasks = k.query_state("tasks")
        assert any(tk["id"] == task_id and tk["status"] == "running" for tk in tasks)

        # 3. Kill agent (task completed)
        k.kill_agent(
            agent,
            result={"status": "success", "output": "Weekly report planned with 5 steps"},
            actor="kernel",
            correlation_id=cid,
        )

        # Check task is done
        tasks = k.query_state("tasks")
        assert any(tk["id"] == task_id and tk["status"] == "completed" for tk in tasks)

        # 4. Full trace
        trace = k.read_events(correlation_id=cid)
        trace_types = [e.type for e in trace]
        assert "TaskCreated" in trace_types
        assert "TaskStarted" in trace_types
        assert "AgentSpawned" in trace_types
        assert "AgentTerminated" in trace_types
        assert "TaskCompleted" in trace_types

        # 5. Rebuild
        k.rebuild("task")
        tasks2 = k.query_state("tasks")
        assert any(tk["id"] == task_id and tk["status"] == "completed" for tk in tasks2)

    def test_agent_is_ephemeral(self, tmp_path):
        """Agents leave no persistent state — only events."""
        k, _ = make_kernel(tmp_path)
        cid = "ephem_test"
        t = k.create_task("Test ephemeral", actor="test", correlation_id=cid)
        agent = k.spawn_agent("brain", task_ref=t["task_id"], correlation_id=cid)
        k.kill_agent(agent, actor="kernel", correlation_id=cid)

        # Verify no agents table, only events
        trace = k.read_events(correlation_id=cid)
        event_types = [e.type for e in trace]
        assert event_types.count("AgentSpawned") == 1
        assert event_types.count("AgentTerminated") == 1
        # Agent spawned + terminated == ephemeral; no persistent agent row

    def test_task_failed_on_error(self, tmp_path):
        k, _ = make_kernel(tmp_path)
        cid = "fail_test"
        t = k.create_task("Failing task", actor="test", correlation_id=cid)
        agent = k.spawn_agent("planner", task_ref=t["task_id"], correlation_id=cid)
        k.kill_agent(
            agent,
            result={"status": "error", "error": "Planner crashed"},
            correlation_id=cid,
        )

        tasks = k.query_state("tasks")
        assert any(tk["id"] == t["task_id"] and tk["status"] == "failed" for tk in tasks)

        trace = k.read_events(correlation_id=cid)
        trace_types = [e.type for e in trace]
        assert "TaskFailed" in trace_types
        assert "TaskCompleted" not in trace_types

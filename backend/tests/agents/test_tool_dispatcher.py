"""Tests for ToolDispatcher and Planner replan."""
from app.core.agents.critic import critic


class TestCriticResetAndIsolation:
    def test_reset_all_tasks(self):
        c = type(critic)()
        import json
        c.audit_step("a", {}, result=json.dumps({"status": "error"}), task_id="t1")
        c.audit_step("b", {}, result=json.dumps({"status": "error"}), task_id="t2")
        c.reset_for_task("")
        assert len(c.failure_history) == 0

    def test_get_failing_tools_empty(self):
        c = type(critic)()
        assert c.get_failing_tools() == set()

    def test_get_failing_tools_global(self):
        c = type(critic)()
        import json
        for _ in range(2):
            c.audit_step("tool_x", {}, result=json.dumps({"status": "error"}), task_id="t1")
        assert "tool_x" in c.get_failing_tools("")

    def test_should_replan_by_rejection_threshold(self):
        c = type(critic)(rejection_threshold=0.1)
        c.audit_step("read_file", {"path": "a"}, task_id="t1")  # pass
        c.audit_step("write_file", {"path": "b"}, task_id="t1")  # reject (no _approved)
        assert c.should_replan("t1") is True

    def test_non_json_result_passes(self):
        c = type(critic)()
        assert c.audit_step("cmd", {"x": 1}, result="plain text output") is True

"""Unit tests for Critic agent — safety rules and self-healing failure detection."""
import json

from app.core.agents.critic import CriticAgent


class TestSafetyRules:
    def test_passes_safe_tool(self):
        c = CriticAgent()
        assert c.audit_step("read_file", {"path": "/tmp/ok.txt"}) is True

    def test_rejects_forbidden_pattern(self):
        c = CriticAgent()
        assert c.audit_step("shell_exec", {"cmd": "rm -rf /"}) is False

    def test_rejects_unapproved_write(self):
        c = CriticAgent()
        assert c.audit_step("write_file", {"path": "/tmp/x.txt"}) is False

    def test_passes_approved_write(self):
        c = CriticAgent()
        assert c.audit_step("write_file", {"path": "/tmp/x.txt", "_approved": True}) is True

    def test_rejects_error_result(self):
        c = CriticAgent()
        error_result = json.dumps({"status": "error", "error": "connection refused"})
        assert c.audit_step("fetch_url", {"url": "http://test"}, result=error_result) is False

    def test_passes_success_result(self):
        c = CriticAgent()
        success_result = json.dumps({"status": "ok", "data": "hello"})
        assert c.audit_step("fetch_url", {"url": "http://test"}, result=success_result) is True

    def test_rejection_rate_zero_initially(self):
        c = CriticAgent()
        assert c.rejection_rate() == 0.0

    def test_rejection_rate_correct(self):
        c = CriticAgent()
        c.audit_step("read_file", {"path": "a"})
        c.audit_step("write_file", {"path": "b"})  # rejected
        assert c.rejection_rate() == 0.5


class TestSelfHealingDetection:
    def test_no_replan_with_few_failures(self):
        c = CriticAgent()
        c.audit_step("fetch_url", {"url": "a"}, result=json.dumps({"status": "error"}), task_id="t1")
        c.audit_step("fetch_url", {"url": "b"}, result=json.dumps({"status": "error"}), task_id="t1")
        assert c.should_replan("t1") is False  # only 2 failures

    def test_replan_after_3_consecutive_failures(self):
        c = CriticAgent()
        for i in range(3):
            c.audit_step("fetch_url", {"url": f"a{i}"}, result=json.dumps({"status": "error"}), task_id="t1")
        assert c.should_replan("t1") is True

    def test_replan_by_rejection_rate(self):
        c = CriticAgent(rejection_threshold=0.2)
        c.audit_step("read_file", {"path": "a"})
        c.audit_step("write_file", {"path": "b"})
        assert c.rejection_rate() == 0.5
        assert c.should_replan() is True

    def test_get_failing_tools(self):
        c = CriticAgent()
        for _ in range(3):
            c.audit_step("fetch_url", {"url": "a"}, result=json.dumps({"status": "error"}), task_id="t1")
        failing = c.get_failing_tools("t1")
        assert "fetch_url" in failing

    def test_reset_for_task(self):
        c = CriticAgent()
        c.audit_step("fetch_url", {"url": "a"}, result=json.dumps({"status": "error"}), task_id="t1")
        c.reset_for_task("t1")
        assert len(c.failure_history) == 0

    def test_forbidden_pattern_records_failure(self):
        c = CriticAgent()
        c.audit_step("shell_exec", {"cmd": "rm -rf /"}, task_id="t1")
        assert len(c.failure_history) == 1
        assert "Forbidden" in c.failure_history[0].error

    def test_task_isolation(self):
        c = CriticAgent()
        c.audit_step("fetch_url", {"url": "a"}, result=json.dumps({"status": "error"}), task_id="t1")
        assert c.should_replan("t2") is False  # different task, no failures

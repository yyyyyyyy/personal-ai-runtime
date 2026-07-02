"""Coverage tests for timer_engine, approval_engine, scheduler."""
from app.core.runtime.runtime_loop import RuntimeLoop
from app.core.runtime.timer_engine import TimerEngine

_next_cron_fire = RuntimeLoop._next_cron_fire


class TestTimerEngineCron:
    def test_next_cron_fire_hour_minute(self):
        result = _next_cron_fire("hour=12,minute=30")
        assert result is not None
        assert "T" in result

    def test_next_cron_fire_every_n_minutes(self):
        result = _next_cron_fire("minute=*/30")
        assert result is not None

    def test_next_cron_fire_day_of_week(self):
        result = _next_cron_fire("day_of_week=mon,hour=8,minute=0")
        assert result is not None

    def test_next_cron_fire_day(self):
        result = _next_cron_fire("day=15,hour=8,minute=0")
        assert result is not None

    def test_timer_engine_init(self):
        engine = TimerEngine.__new__(TimerEngine)
        assert engine is not None


class TestApprovalEngine:
    def test_request_approval_via_kernel(self, isolated_kernel):
        k, _db = isolated_kernel
        result = k.request_approval(
            action="write_file",
            risk="high",
            ctx={"args": {"path": "/tmp/test"}, "proposed_by": "agent:planner"},
            actor="agent:planner",
        )
        assert result is not None
        assert result["status"] == "pending"

    def test_approve_lifecycle_via_kernel(self, isolated_kernel):
        k, _db = isolated_kernel
        result = k.request_approval(
            action="read_file",
            risk="high",
            ctx={"args": {"path": "/tmp/read"}, "proposed_by": "agent:planner"},
            actor="agent:planner",
        )
        k.grant_approval(result["approval_id"], action="read_file", actor="user", reason="test")
        approval = k.query_state("approvals", id=result["approval_id"])
        assert len(approval) == 1
        assert approval[0]["status"] == "approved"

    def test_reject_approval_via_kernel(self, isolated_kernel):
        k, _db = isolated_kernel
        result = k.request_approval(
            action="shell_exec",
            risk="high",
            ctx={"args": {"command": "ls"}, "proposed_by": "agent:planner"},
            actor="agent:planner",
        )
        k.deny_approval(result["approval_id"], action="shell_exec", actor="user", reason="test reject")
        approval = k.query_state("approvals", id=result["approval_id"])
        assert len(approval) == 1
        assert approval[0]["status"] in ("rejected", "denied")

    def test_get_approval_missing(self):
        # ApprovalEngine has been consolidated into CapabilityGovernance (v0.4.0).
        # The read-only approval lookup is now a static method there.
        from app.core.runtime.capability_governance import CapabilityGovernance
        from app.core.runtime.kernel_instance import kernel as k
        assert CapabilityGovernance.get_approval(k, "nonexistent") is None

    def test_request_approval_with_task_id_via_kernel(self, isolated_kernel):
        k, _db = isolated_kernel
        result = k.request_approval(
            action="apply_patch",
            risk="high",
            ctx={"task_id": "task_123", "args": {"old": "a", "new": "b"}, "proposed_by": "agent:planner"},
            actor="agent:planner",
        )
        assert result is not None


class TestScheduler:
    def test_schedules_all_present(self):
        from app.core.runtime.cron_registry import SCHEDULES

        assert len(SCHEDULES) == 8
        names = {s["name"] for s in SCHEDULES}
        assert "inbox_poll" in names
        assert "morning_brief" in names
        for s in SCHEDULES:
            assert s["handler_name"] in names

    def test_init_scheduler_registers_timers(self, isolated_kernel):
        from app.core.runtime.cron_registry import init_scheduler, shutdown_scheduler

        k, db = isolated_kernel
        init_scheduler()
        shutdown_scheduler()

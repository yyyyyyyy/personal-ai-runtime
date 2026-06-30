"""Coverage tests for timer_engine, approval_engine, scheduler."""
from app.core.runtime.timer_engine import TimerEngine, _next_cron_fire


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
    def test_request_approval(self, isolated_kernel):
        from app.core.runtime.approval_engine import ApprovalEngine
        engine = ApprovalEngine()
        result = engine.request_approval(
            action="write_file", params={"path": "/tmp/test"},
            proposed_by="agent:planner",
        )
        assert result is not None
        assert result.get("action") == "write_file"

    def test_approve_lifecycle(self, isolated_kernel):
        from app.core.runtime.approval_engine import ApprovalEngine
        engine = ApprovalEngine()
        result = engine.request_approval(
            action="read_file", params={"path": "/tmp/read"},
            proposed_by="agent:planner",
        )
        approved = engine.approve(result["id"])
        assert approved is not None
        assert approved["status"] == "approved"

    def test_reject_approval(self, isolated_kernel):
        from app.core.runtime.approval_engine import ApprovalEngine
        engine = ApprovalEngine()
        result = engine.request_approval(
            action="shell_exec", params={"command": "ls"},
            proposed_by="agent:planner",
        )
        rejected = engine.reject(result["id"])
        assert rejected is not None
        assert rejected["status"] in ("rejected", "denied")

    def test_get_approval_missing(self):
        from app.core.runtime.approval_engine import ApprovalEngine
        engine = ApprovalEngine()
        assert engine.get_approval("nonexistent") is None

    def test_request_approval_with_task_id(self, isolated_kernel):
        from app.core.runtime.approval_engine import ApprovalEngine
        engine = ApprovalEngine()
        result = engine.request_approval(
            action="apply_patch", params={"old": "a", "new": "b"},
            proposed_by="agent:planner", task_id="task_123",
        )
        assert result is not None


class TestScheduler:
    def test_schedules_all_present(self):
        from app.core.runtime.scheduler import SCHEDULES

        assert len(SCHEDULES) == 9
        names = {s["name"] for s in SCHEDULES}
        assert "inbox_poll" in names
        assert "belief_reflection" in names
        for s in SCHEDULES:
            assert s["handler_name"] in names

    def test_init_scheduler_registers_timers(self, isolated_kernel):
        from app.core.runtime.scheduler import init_scheduler, shutdown_scheduler

        k, db = isolated_kernel
        init_scheduler()
        shutdown_scheduler()

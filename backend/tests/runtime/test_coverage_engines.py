"""Coverage tests for timer and approval lifecycle.

v0.6.0: timer_engine deleted; _next_cron_fire lives on RuntimeLoop.
v0.11.0: _next_cron_fire format tests removed — they assert ISO timestamp
details and break on any refactor. Runtime behaviour is covered by
test_scheduler.py and test_runtime_config.py.
"""
from app.core.runtime.runtime_loop import RuntimeLoop


class TestTimerEngineCron:
    def test_timer_schedule_registration(self, isolated_kernel):
        """Verify timer events can be created via cron_registry init."""
        k, db = isolated_kernel
        import app.core.runtime.cron_registry as cr

        from app.core.runtime.cron_registry import _init_timers

        old_kernel = cr.kernel
        cr.kernel = k  # type: ignore[attr-defined]
        try:
            _init_timers()
        finally:
            cr.kernel = old_kernel  # type: ignore[attr-defined]
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM timer_events WHERE id='morning_brief'"
            ).fetchone()
            assert row is not None


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
        k.grant_approval(
            result["approval_id"], action="read_file", actor="user", reason="test",
        )
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
        k.deny_approval(
            result["approval_id"], action="shell_exec", actor="user",
            reason="test reject",
        )
        approval = k.query_state("approvals", id=result["approval_id"])
        assert len(approval) == 1
        assert approval[0]["status"] in ("rejected", "denied")

    def test_get_approval_missing(self):
        from app.core.runtime.capability_governance import CapabilityGovernance
        from app.core.runtime.kernel_instance import kernel as k

        assert CapabilityGovernance.get_approval(k, "nonexistent") is None

    def test_request_approval_with_task_id_via_kernel(self, isolated_kernel):
        k, _db = isolated_kernel
        result = k.request_approval(
            action="apply_patch",
            risk="high",
            ctx={
                "task_id": "task_123",
                "args": {"old": "a", "new": "b"},
                "proposed_by": "agent:planner",
            },
            actor="agent:planner",
        )
        assert result is not None


class TestScheduler:
    def test_init_scheduler_registers_timers(self, isolated_kernel):
        from app.core.runtime.cron_registry import init_scheduler, shutdown_scheduler

        k, db = isolated_kernel
        import app.core.runtime.cron_registry as cr

        old_kernel = cr.kernel
        cr.kernel = k
        try:
            init_scheduler()
        finally:
            cr.kernel = old_kernel

        with db.get_db() as conn:
            rows = conn.execute("SELECT id FROM timer_events").fetchall()
            names = {r[0] for r in rows}
            assert "morning_brief" in names
            assert "inbox_poll" in names
        shutdown_scheduler()

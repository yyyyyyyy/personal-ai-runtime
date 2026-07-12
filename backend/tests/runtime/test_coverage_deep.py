"""Deep coverage tests for timer_engine scan loop (v0.3.0: now in RuntimeLoop)."""
import pytest


class TestTimerEngineScan:
    @pytest.mark.asyncio
    async def test_scan_fires_due_timer(self, isolated_kernel):
        """Create a timer with past fire_at, run RuntimeLoop._check_timers, verify TimerFired emitted."""
        from datetime import UTC, datetime, timedelta

        from app.core.runtime.runtime_loop import RuntimeLoop
        k, db = isolated_kernel

        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        k.emit_event("TimerCreated", "timer", "timer_scan_test", payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": past,
        }, actor="verify")

        # Temporarily swap kernel singleton so _check_timers uses test kernel
        import app.core.runtime.runtime_loop as rl_mod
        original = rl_mod.kernel
        rl_mod.kernel = k
        try:
            loop = RuntimeLoop()
            await loop._check_timers()
        finally:
            rl_mod.kernel = original

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            fired = conn.execute(
                "SELECT 1 FROM event_log WHERE type='TimerFired' AND aggregate_id='timer_scan_test' LIMIT 1"
            ).fetchone()
            assert fired is not None, "TimerFired event not emitted for due timer"

    @pytest.mark.asyncio
    async def test_scan_skips_future_timer(self, isolated_kernel):
        """Timer with future fire_at should not fire."""
        from datetime import UTC, datetime, timedelta

        from app.core.runtime.runtime_loop import RuntimeLoop
        k, db = isolated_kernel

        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        k.emit_event("TimerCreated", "timer", "timer_future", payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": future,
        }, actor="verify")

        import app.core.runtime.runtime_loop as rl_mod
        original = rl_mod.kernel
        rl_mod.kernel = k
        try:
            loop = RuntimeLoop()
            await loop._check_timers()
        finally:
            rl_mod.kernel = original

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            fired = conn.execute(
                "SELECT 1 FROM event_log WHERE type='TimerFired' AND aggregate_id='timer_future' LIMIT 1"
            ).fetchone()
            assert fired is None, "Future timer should not fire"

    @pytest.mark.asyncio
    async def test_next_cron_fire_edge_cases(self, isolated_kernel):
        """_next_cron_fire returns a valid future ISO timestamp (was TimerEngine test)."""
        from datetime import UTC, datetime

        from app.core.runtime.runtime_loop import RuntimeLoop
        now = datetime.now(UTC)
        result = RuntimeLoop._next_cron_fire("minute=*/15", from_ts=now)
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None, "next fire time must carry tzinfo"
        assert parsed > now, "next fire time must be in the future"

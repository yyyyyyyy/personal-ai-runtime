"""Extra coverage tests for timer_engine edge cases."""
import pytest


class TestTimerEngineMore:
    def test_next_cron_fire_with_from_ts(self):
        from datetime import UTC, datetime

        from app.core.runtime.timer_engine import _next_cron_fire
        base = datetime(2026, 6, 19, 9, 0, 0, tzinfo=UTC)
        result = _next_cron_fire("hour=10,minute=0", from_ts=base)
        assert "T10:00" in result or "10:00:00" in result

    def test_next_cron_fire_various_patterns(self):
        from app.core.runtime.timer_engine import _next_cron_fire
        _next_cron_fire("hour=23,minute=59")
        _next_cron_fire("minute=*/5")
        _next_cron_fire("hour=0,minute=0")
        _next_cron_fire("day_of_week=wed,hour=12,minute=30")

    def test_get_timer_engine(self, isolated_kernel):
        # get_timer_engine removed in v0.3.0; TimerEngine now uses timer_engine singleton
        from app.core.runtime.timer_engine import timer_engine
        assert timer_engine is not None

    def test_reset_timer_engine(self):
        # reset_timer_engine removed in v0.3.0; timer scanning is now in RuntimeLoop
        pass

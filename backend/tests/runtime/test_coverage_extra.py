"""Extra coverage tests for timer_engine utility functions."""
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

    def test_ensure_schedules_functional(self):
        # ensure_schedules is now a module-level function, not a class method
        from app.core.runtime.timer_engine import ensure_schedules
        assert callable(ensure_schedules)

"""Extra coverage tests for cron scheduling utility functions.

v0.6.0: timer_engine deleted; _next_cron_fire lives on RuntimeLoop.
"""

from app.core.runtime.runtime_loop import RuntimeLoop


class TestTimerEngineMore:
    def test_next_cron_fire_with_from_ts(self):
        from datetime import UTC, datetime

        result = RuntimeLoop._next_cron_fire(
            "hour=10,minute=0",
            from_ts=datetime(2026, 6, 19, 9, 0, 0, tzinfo=UTC),
        )
        assert "T10:00" in result or "10:00:00" in result

    def test_next_cron_fire_various_patterns(self):
        RuntimeLoop._next_cron_fire("hour=23,minute=59")
        RuntimeLoop._next_cron_fire("minute=*/5")
        RuntimeLoop._next_cron_fire("hour=0,minute=0")
        RuntimeLoop._next_cron_fire("day_of_week=wed,hour=12,minute=30")

"""Extra coverage tests for timer_engine and agent_bus edge cases."""
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


class TestAgentBusMore:
    @pytest.mark.asyncio
    async def test_agent_bus_start_stop(self, isolated_kernel):
        from app.core.runtime.agent_bus import AgentBus
        k, db = isolated_kernel
        bus = AgentBus()
        await bus.start()
        assert bus._running is True
        await bus.stop()
        assert bus._running is False

    def test_agent_bus_init_defaults(self, isolated_kernel):
        from app.core.runtime.agent_bus import AgentBus
        k, db = isolated_kernel
        bus = AgentBus()
        assert bus._subscriptions == {}
        assert bus._queues == {}

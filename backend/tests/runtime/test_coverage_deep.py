"""Deep coverage tests for timer_engine scan loop and agent_bus publish/subscribe."""
import pytest


class TestTimerEngineScan:
    @pytest.mark.asyncio
    async def test_scan_fires_due_timer(self, isolated_kernel):
        """Create a timer with past fire_at, start engine, verify TimerFired emitted."""
        from datetime import UTC, datetime, timedelta

        from app.core.runtime.timer_engine import TimerEngine
        k, db = isolated_kernel

        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        k.emit_event("TimerCreated", "timer", "timer_scan_test", payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": past,
        }, actor="verify")

        engine = TimerEngine(k)
        # Run one scan iteration manually
        engine._running = True
        await engine._check_and_fire()

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

        from app.core.runtime.timer_engine import TimerEngine
        k, db = isolated_kernel

        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        k.emit_event("TimerCreated", "timer", "timer_future", payload={
            "handler_name": "test_handler",
            "schedule_type": "cron",
            "cron_expr": "hour=0,minute=0",
            "fire_at": future,
        }, actor="verify")

        engine = TimerEngine(k)
        engine._running = True
        await engine._check_and_fire()

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            fired = conn.execute(
                "SELECT 1 FROM event_log WHERE type='TimerFired' AND aggregate_id='timer_future' LIMIT 1"
            ).fetchone()
            assert fired is None, "Future timer should not fire"

    @pytest.mark.asyncio
    async def test_timer_engine_start_stop(self, isolated_kernel):
        """TimerEngine start/stop lifecycle."""
        from app.core.runtime.timer_engine import TimerEngine
        k, db = isolated_kernel
        engine = TimerEngine(k)
        await engine.start()
        assert engine._running is True
        assert engine._task is not None
        await engine.stop()
        assert engine._running is False


class TestAgentBusPublish:
    @pytest.mark.asyncio
    async def test_publish_to_subscriber(self, isolated_kernel):
        """Subscriber receives published events via AgentBus."""
        from app.core.runtime.agent_bus import AgentBus
        from app.core.runtime.agent_definition import SubscriptionRule
        k, db = isolated_kernel

        bus = AgentBus()
        received = []

        async def my_handler(event):
            received.append(event.type)

        rule = SubscriptionRule(event_type="GoalCreated")
        bus.subscribe("test_agent", rule, my_handler)

        evt = k.emit_event("GoalCreated", "goal", "goal_pub", payload={
            "title": "Pub test",
        }, actor="verify")

        await bus.publish(evt)
        assert "GoalCreated" in received

    @pytest.mark.asyncio
    async def test_publish_no_match(self, isolated_kernel):
        """Event not matching any subscription should not crash."""
        from app.core.runtime.agent_bus import AgentBus
        from app.core.runtime.agent_definition import SubscriptionRule
        k, db = isolated_kernel

        bus = AgentBus()
        received = []

        rule = SubscriptionRule(event_type="TaskCreated")
        bus.subscribe("test_agent", rule, lambda e: received.append(e.type))

        evt = k.emit_event("GoalCreated", "goal", "goal_nomatch", payload={
            "title": "No match",
        }, actor="verify")

        await bus.publish(evt)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_publish_aggregate_type_filter(self, isolated_kernel):
        """SubscriptionRule with aggregate_type filter."""
        from app.core.runtime.agent_bus import AgentBus
        from app.core.runtime.agent_definition import SubscriptionRule
        k, db = isolated_kernel

        bus = AgentBus()
        received = []

        rule = SubscriptionRule(aggregate_type="goal")
        bus.subscribe("test_agent", rule, lambda e: received.append(e.aggregate_type))

        evt = k.emit_event("GoalCreated", "goal", "goal_agg", payload={
            "title": "Agg filter",
        }, actor="verify")

        await bus.publish(evt)
        assert "goal" in received

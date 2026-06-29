"""Coverage tests for agent_bus, legacy_event_adapter edge cases."""
import pytest


class TestAgentBus:
    def test_agent_bus_init(self):
        from app.core.runtime.agent_bus import AgentBus
        bus = AgentBus()
        assert bus is not None
        assert not bus._running

    def test_agent_bus_default_transport(self):
        from app.core.runtime.agent_bus import AgentBus
        bus = AgentBus()
        assert bus._transport is not None


class TestLegacyEventAdapter:
    def test_to_legacy_dict(self, isolated_kernel):
        from app.core.runtime.legacy_event_adapter import to_legacy_dict
        k, db = isolated_kernel
        evt = k.emit_event("GoalCreated", "goal", "goal_leg", payload={"title": "Legacy"}, actor="verify")
        d = to_legacy_dict(evt)
        assert isinstance(d, dict)
        assert "type" in d

    def test_recent_legacy_events_with_type(self, isolated_kernel):
        from app.core.runtime.legacy_event_adapter import recent_legacy_events
        k, db = isolated_kernel
        k.emit_event("GoalCreated", "goal", "goal_leg2", payload={"title": "Legacy2"}, actor="verify")
        result = recent_legacy_events(k.read_events, event_type="GoalCreated", days=7, limit=10)
        assert isinstance(result, list)

    def test_goal_legacy_events(self, isolated_kernel):
        from app.core.runtime.legacy_event_adapter import goal_legacy_events
        k, db = isolated_kernel
        k.emit_event("GoalCreated", "goal", "goal_leg3", payload={"title": "Legacy3"}, actor="verify")
        result = goal_legacy_events("goal_leg3", limit=20)
        assert isinstance(result, list)

    def test_recent_legacy_events_include_application(self, isolated_kernel):
        from app.core.runtime.legacy_event_adapter import recent_legacy_events
        k, db = isolated_kernel
        result = recent_legacy_events(k.read_events, include_application=True, days=7, limit=10)
        assert isinstance(result, list)

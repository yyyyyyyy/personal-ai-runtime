"""W4 — Single Event Plane convergence tests."""

import asyncio
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.event_bus import event_bus
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.legacy_event_adapter import goal_legacy_events, to_legacy_dict
from app.core.runtime.task_engine import task_engine


@pytest.fixture
async def wired_event_bus():
    """Isolate global EventBus between async tests."""
    await event_bus.stop()
    event_bus._subscribers.clear()
    event_bus._queue = asyncio.Queue()
    await event_bus.start()
    yield event_bus
    await event_bus.stop()


@pytest.mark.asyncio
async def test_dependency_unlock_via_kernel(wired_event_bus):
    """C1: dependency unlock uses kernel.subscribe_events (sync handler)."""
    from app.core.runtime.scheduler import _on_task_completed

    kernel.subscribe_events(_on_task_completed, type="TaskCompleted")
    kernel.subscribe_events(_on_task_completed, type="TaskStatusChanged")

    dep = task_engine.create_task(name="Dep Task")
    dependent = task_engine.create_task(name="Dependent Task", dependencies=[dep["id"]])
    assert dependent["status"] == "pending"

    task_engine.update_task_status(dep["id"], "running")
    task_engine.update_task_status(dep["id"], "completed")

    # Handler is sync — dependent task starts immediately via kernel dispatch
    updated = task_engine.get_task(dependent["id"])
    assert updated is not None
    assert updated["status"] == "running"


def test_goal_events_from_event_log():
    goal_id = kernel.emit_event(
        "GoalCreated",
        "goal",
        "w4-test-goal",
        payload={"title": "W4 Goal", "status": "active", "created_at": "2026-01-01T00:00:00"},
        actor="test",
    ).aggregate_id

    rows = goal_legacy_events(goal_id, limit=5)
    assert len(rows) >= 1
    assert rows[0]["type"] == "goal_created"
    assert rows[0]["goal_id"] == goal_id


def test_legacy_adapter_capability_invoked():
    event = kernel.emit_event(
        "CapabilityInvoked",
        "capability",
        "cap-1",
        payload={"name": "web_search", "status": "success"},
        actor="test",
    )
    legacy = to_legacy_dict(event)
    assert legacy["type"] == "tool_call"
    assert "web_search" in legacy["summary"]


def test_goal_legacy_events_uses_payload_goal_id_filter():
    goal_id = kernel.emit_event(
        "GoalCreated",
        "goal",
        "goal-filter-test",
        payload={"title": "Filter Goal", "created_at": "2026-01-01T00:00:00"},
        actor="test",
    ).aggregate_id
    _action_id = kernel.emit_event(
        "ActionCreated",
        "action",
        "action-filter-test",
        payload={"goal_id": goal_id, "title": "Scoped Action", "status": "pending"},
        actor="test",
    ).aggregate_id

    rows = goal_legacy_events(goal_id, limit=10)
    types = {r["type"] for r in rows}
    assert "goal_created" in types
    assert "action_created" in types
    assert any(r.get("goal_id") == goal_id for r in rows if r["type"] == "action_created")


def test_legacy_type_filter_maps_goal_completed():
    goal_id = kernel.emit_event(
        "GoalCompleted",
        "goal",
        "completed-filter-goal",
        payload={"status": "completed"},
        actor="test",
    ).aggregate_id
    rows = goal_legacy_events(goal_id, limit=5)
    assert any(r["type"] == "goal_status_changed" for r in rows)


def test_read_events_since_ts_and_limit():
    kernel.emit_event("GoalCreated", "goal", "ts-goal-1", payload={"title": "A"}, actor="test")
    events = kernel.read_events(since_ts="2020-01-01T00:00:00", limit=3, order="desc")
    assert len(events) <= 3
    if len(events) > 1:
        assert events[0].seq >= events[-1].seq

"""W4 — Single Event Plane convergence tests."""

import asyncio
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

import app.core.runtime.kernel_event_bridge as kernel_event_bridge_mod
from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_event_bridge import register_kernel_event_bridge
from app.core.runtime.legacy_event_adapter import goal_legacy_events, to_legacy_dict
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.task_engine import task_engine


@pytest.fixture
async def wired_event_bus():
    """Isolate global EventBus + Kernel bridge between async tests."""
    await event_bus.stop()
    event_bus._subscribers.clear()
    event_bus._queue = asyncio.Queue()
    kernel_event_bridge_mod._bridge_unsubscribe = None

    await event_bus.start()
    register_kernel_event_bridge()
    yield event_bus
    await event_bus.stop()


@pytest.mark.asyncio
async def test_kernel_bridge_publishes_task_completed(wired_event_bus):
    received: list[dict] = []

    async def handler(_event_type: str, payload: dict):
        received.append(payload)

    wired_event_bus.subscribe(EventType.TASK_COMPLETED, handler)

    task = task_engine.create_task(name="Bridge Test")
    task_engine.update_task_status(task["id"], "running")
    task_engine.update_task_status(task["id"], "completed")

    await asyncio.sleep(0.3)
    assert any(p.get("task_id") == task["id"] for p in received)


@pytest.mark.asyncio
async def test_dependency_unlock_via_bridge(wired_event_bus):
    from app.core.runtime.scheduler_v2 import _on_task_completed

    wired_event_bus.subscribe(EventType.TASK_COMPLETED, _on_task_completed)

    dep = task_engine.create_task(name="Dep Task")
    dependent = task_engine.create_task(name="Dependent Task", dependencies=[dep["id"]])
    assert dependent["status"] == "pending"

    task_engine.update_task_status(dep["id"], "running")
    task_engine.update_task_status(dep["id"], "completed")

    await asyncio.sleep(0.5)
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
    action_id = kernel.emit_event(
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

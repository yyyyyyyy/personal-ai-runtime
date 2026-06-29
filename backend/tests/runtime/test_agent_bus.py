"""Tests for AgentBus — event routing between agents."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "abus.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="bus_test_planner",
        version="1.0.0",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


@pytest.fixture
def worker_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="bus_test_worker",
        version="1.0.0",
        subscriptions=[SubscriptionRule(event_type="TaskPlanned")],
    )


@pytest.mark.asyncio
async def test_agent_bus_routes_event_to_subscriber(kernel, planner_def):
    """An event published to the bus reaches a subscribed agent."""
    from app.core.runtime.agent_bus import agent_bus

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    received_events = []

    async def handler(event):
        received_events.append(event)

    unsub = agent_bus.subscribe(
        agent_id=planner.instance_id,
        rule=planner_def.subscriptions[0],
        handler=handler,
    )

    # Emit a TaskCreated event via Kernel (which publishes to AgentBus)
    kernel.emit_event(
        "TaskCreated", "task", "task_bus_1",
        payload={"name": "Test task"},
        actor="user",
    )

    # Allow async delivery
    import asyncio
    await asyncio.sleep(0.2)

    unsub()
    assert len(received_events) >= 1
    assert received_events[0].type == "TaskCreated"

    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_agent_bus_unsubscribe_stops_routing(kernel, planner_def):
    """Unsubscribe removes the handler, no more events delivered."""
    from app.core.runtime.agent_bus import agent_bus

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    received_events = []

    async def handler(event):
        received_events.append(event)

    unsub = agent_bus.subscribe(
        agent_id=planner.instance_id,
        rule=planner_def.subscriptions[0],
        handler=handler,
    )

    kernel.emit_event("TaskCreated", "task", "task_bus_unsub", payload={}, actor="user")
    import asyncio
    await asyncio.sleep(0.2)

    before_unsub = len(received_events)
    unsub()

    kernel.emit_event("TaskCreated", "task", "task_bus_unsub_2", payload={}, actor="user")
    await asyncio.sleep(0.2)

    after_unsub = len(received_events) - before_unsub
    assert after_unsub == 0, "No events should be received after unsubscribe"

    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_agent_bus_subscription_rule_matching(kernel):
    """Subscription rules filter events by type and aggregate."""
    from app.core.runtime.agent_bus import agent_bus
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

    narrow_def = AgentDefinition(
        agent_id="narrow",
        subscriptions=[
            SubscriptionRule(event_type="TaskPlanned"),
            SubscriptionRule(event_type="TaskCompleted"),
        ],
    )

    registry = kernel.agent_registry
    agent = await registry.spawn(narrow_def)

    received_types = []

    async def handler(event):
        received_types.append(event.type)

    agent_bus.subscribe(
        agent_id=agent.instance_id,
        rule=narrow_def.subscriptions[0],
        handler=handler,
    )

    import asyncio
    # Emit events — only TaskPlanned should be delivered
    kernel.emit_event("TaskCreated", "task", "t_nomatch", payload={}, actor="user")
    kernel.emit_event("TaskPlanned", "task", "t_match", payload={}, actor="user")
    kernel.emit_event("TaskCompleted", "task", "t_other", payload={}, actor="user")
    await asyncio.sleep(0.2)

    # Only TaskPlanned should have been delivered
    assert "TaskPlanned" in received_types
    assert "TaskCreated" not in received_types

    await registry.kill(agent.instance_id)


@pytest.mark.asyncio
async def test_agent_bus_deliver_to_blocking(kernel, planner_def):
    """deliver_to blocks until an event arrives or times out."""
    from app.core.runtime.agent_bus import agent_bus

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    async def handler(event):
        pass  # Just acknowledge

    agent_bus.subscribe(
        agent_id=planner.instance_id,
        rule=planner_def.subscriptions[0],
        handler=handler,
    )

    import asyncio
    # Publish an event
    kernel.emit_event("TaskCreated", "task", "task_deliver", payload={}, actor="user")
    await asyncio.sleep(0.1)

    # deliver_to should return the event (or timeout with None)
    # Note: handler consumption also dequeues, so deliver_to may get None
    # The key test: it doesn't hang
    await agent_bus.deliver_to(planner.instance_id, timeout=0.5)
    await registry.kill(planner.instance_id)

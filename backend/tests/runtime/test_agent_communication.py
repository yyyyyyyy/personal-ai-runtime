"""Tests for Agent Communication — Planner ↔ Worker via AgentBus.

Validates the end-to-end event-driven communication:
    TaskCreated → Planner → TaskPlanned → Worker → TaskCompleted
"""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the global scheduler singleton between tests.

    agent_bus is cleaned by conftest._reset_runtime via RuntimeContainer.
    """
    from app.core.runtime.agent_scheduler import reset_scheduler
    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "comms.db")))


@pytest.mark.asyncio
async def test_planner_to_worker_event_chain(kernel):
    """Full event chain: TaskCreated → Planner → TaskPlanned → Worker → TaskCompleted."""
    # Import triggers @subscribe registration
    import app.core.agents.mvp.planner_agent  # noqa: F401 — registers handlers
    import app.core.agents.mvp.worker_agent  # noqa: F401 — registers handlers
    from app.core.agents.mvp import PLANNER_DEFINITION, WORKER_DEFINITION
    from app.core.runtime.agent_bus import agent_bus
    from app.core.runtime.agent_scheduler import get_scheduler

    registry = kernel.agent_registry
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    planner = await registry.spawn(PLANNER_DEFINITION)
    worker = await registry.spawn(WORKER_DEFINITION)

    # Subscribe via instance.dispatch — event routing is done by HandlerRegistry
    agent_bus.subscribe(
        agent_id=planner.instance_id,
        rule=PLANNER_DEFINITION.subscriptions[0],
        handler=lambda e: planner.dispatch(e),
    )
    agent_bus.subscribe(
        agent_id=worker.instance_id,
        rule=WORKER_DEFINITION.subscriptions[0],
        handler=lambda e: worker.dispatch(e),
    )

    # Kick off: emit TaskCreated
    event = kernel.emit_event(
        "TaskCreated",
        "task",
        "task_chain_1",
        payload={"name": "Test chain task"},
        actor="user",
    )
    assert event.type == "TaskCreated"

    await scheduler.flush()
    # The chain is: dispatch creates WorkItems → Scheduler processes them
    # Planner handle triggers emit(TaskPlanned) which goes through AgentBus
    # Worker picks it up and emits TaskCompleted
    # Need additional flushes + event loop yields for cascading events
    import asyncio
    await asyncio.sleep(0.1)
    await scheduler.flush()
    await asyncio.sleep(0.1)
    await scheduler.flush()

    # Verify the event chain exists in event_log
    all_events = kernel.read_events(aggregate_type="task")

    # TaskCreated should be there
    created = [e for e in all_events if e.type == "TaskCreated"]
    assert len(created) >= 1

    # TaskPlanned should be emitted by Planner
    planned = [e for e in all_events if e.type == "TaskPlanned"]
    assert len(planned) >= 1
    assert planned[0].actor.startswith("agent:")

    # TaskCompleted should be emitted by Worker
    completed = [e for e in all_events if e.type == "TaskCompleted"]
    assert len(completed) >= 1

    # Audit chain: all events share the same task_chain_1 aggregate
    task_events = [e for e in all_events if e.aggregate_id == "task_chain_1"]
    assert len(task_events) >= 3

    await registry.kill(planner.instance_id)
    await registry.kill(worker.instance_id)
    await scheduler.stop()
async def test_agent_communication_via_agent_manager(kernel):
    """AgentManager orchestrates Planner + Worker via AgentBus."""
    from app.core.runtime.agent_manager import AgentManager

    manager = AgentManager(kernel)
    result = await manager.run(user_request="Test multi-agent task")

    assert result["status"] == "ok"
    assert result["planner_events"] > 0 or result["worker_events"] > 0

    # Verify the complete event chain is in the log
    events = kernel.read_events()
    event_types = {e.type for e in events}
    assert "TaskCreated" in event_types
    assert "TaskPlanned" in event_types
    assert "TaskCompleted" in event_types


@pytest.mark.asyncio
async def test_correlation_id_preserved(kernel):
    """Events in the same pipeline share the same correlation_id for auditability."""
    from app.core.runtime.agent_manager import AgentManager

    manager = AgentManager(kernel)
    result = await manager.run(user_request="Audit trail test")

    correlation_id = result["correlation_id"]
    assert correlation_id is not None

    # All events in this pipeline should have the same correlation_id
    events = kernel.read_events(correlation_id=correlation_id)
    assert len(events) >= 1
    for e in events:
        assert e.correlation_id == correlation_id

"""Tests for AgentInstance — state isolation, event log independence, checkpoint."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "ainst.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="test_planner",
        version="1.0.0",
        tools=["web_search"],
        subscriptions=[
            SubscriptionRule(event_type="TaskCreated"),
            SubscriptionRule(event_type="TaskCompleted"),
        ],
    )


@pytest.fixture
def worker_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="test_worker",
        version="1.0.0",
        tools=["web_search"],
        subscriptions=[
            SubscriptionRule(event_type="TaskPlanned"),
        ],
    )


@pytest.mark.asyncio
async def test_agent_emits_event_with_actor_tag(kernel, planner_def):
    """Agent events carry agent:<instance_id> as actor for isolation."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    event = await planner.emit(
        event_type="TaskPlanned",
        aggregate_type="task",
        aggregate_id="task_001",
        payload={"plan": "test"},
    )

    assert event.actor.startswith("agent:")
    assert planner.instance_id in event.actor
    assert event.type == "TaskPlanned"

    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_agent_state_isolation(kernel, planner_def, worker_def):
    """Planner and Worker should have independent event streams."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    worker = await registry.spawn(worker_def)

    # Planner emits events
    await planner.emit("TaskPlanned", "task", "task_001", {"from": "planner"})
    await planner.emit("TaskPlanned", "task", "task_002", {"from": "planner"})

    # Worker emits events
    await worker.emit("TaskCompleted", "task", "task_003", {"from": "worker"})

    # Planner only sees its own events
    planner_events = planner.kernel.read_events(aggregate_type="task")
    planner_filtered = [e for e in planner_events if e.actor == planner.actor_id()]
    assert len(planner_filtered) == 2
    assert all(e.actor.startswith("agent:") for e in planner_filtered)

    # Worker only sees its own events
    worker_events = worker.kernel.read_events(aggregate_type="task")
    worker_filtered = [e for e in worker_events if e.actor == worker.actor_id()]
    assert len(worker_filtered) == 1

    await registry.kill(planner.instance_id)
    await registry.kill(worker.instance_id)


@pytest.mark.asyncio
async def test_agent_checkpoint_independent(kernel, planner_def, worker_def):
    """Planner and Worker checkpoints are stored independently."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    worker = await registry.spawn(worker_def)

    await planner.emit("TaskPlanned", "task", "task_ck_1", {"from": "planner"})
    await worker.emit("TaskCompleted", "task", "task_ck_2", {"from": "worker"})

    # Save per-agent checkpoints
    planner_ck = await planner.save_checkpoint("task")
    worker_ck = await worker.save_checkpoint("task")

    assert planner_ck["agent_id"] == planner.instance_id
    assert worker_ck["agent_id"] == worker.instance_id
    assert planner_ck["agent_id"] != worker_ck["agent_id"]

    # Verify checkpoint sequences are independent
    planner_seq = await planner.get_checkpoint_seq("task")
    worker_seq = await worker.get_checkpoint_seq("task")
    assert planner_seq > 0
    assert worker_seq > 0

    await registry.kill(planner.instance_id)
    await registry.kill(worker.instance_id)


@pytest.mark.asyncio
async def test_agent_lifecycle_status_transitions(kernel, planner_def):
    """Agent instance status transitions correctly through its lifecycle."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    assert planner.status == "running"

    await planner.pause()
    assert planner.status == "paused"

    await planner.resume()
    assert planner.status == "running"

    await registry.kill(planner.instance_id)
    assert planner.status == "terminated"
    assert registry.get(planner.instance_id) is None

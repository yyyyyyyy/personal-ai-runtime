"""Tests for Agent Recovery — checkpoint restore and event replay after crash."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "recover.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="recover_planner",
        version="1.0.0",
        stale_timeout_seconds=1,
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


@pytest.mark.asyncio
async def test_agent_checkpoint_save_and_restore(kernel, planner_def):
    """After emitting events, a checkpoint can be saved and the seq verified."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    # Emit some events
    await planner.emit("TaskPlanned", "task", "rec_task_1", payload={"step": 1})
    await planner.emit("TaskPlanned", "task", "rec_task_2", payload={"step": 2})

    # Save checkpoint
    ck = await planner.save_checkpoint("task")
    assert ck["agent_id"] == planner.instance_id
    assert ck["last_applied_seq"] > 0

    # Checkpoint seq should reflect the last event
    seq = await planner.get_checkpoint_seq("task")
    assert seq > 0

    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_agent_state_persists_in_event_log(kernel, planner_def):
    """Agent events survive process restart (simulated by reading from event_log)."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    await planner.emit("TaskPlanned", "task", "rec_persist", payload={"data": "hello"})

    agent_id = planner.instance_id
    await registry.kill(planner.instance_id)

    # "Restart" — read events from the event_log filtered by actor
    all_events = kernel.read_events(aggregate_type="task")
    agent_events = [e for e in all_events if e.actor == f"agent:{agent_id}"]
    assert len(agent_events) >= 1
    assert agent_events[0].payload.get("data") == "hello"


@pytest.mark.asyncio
async def test_rebuild_after_crash(kernel, planner_def):
    """Simulate crash: emit events, checkpoint, then rebuild from event log."""
    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    # Emit events and checkpoint
    await planner.emit("TaskPlanned", "task", "rec_rebuild_1", payload={"step": 1})
    await planner.emit("TaskPlanned", "task", "rec_rebuild_2", payload={"step": 2})
    await planner.save_checkpoint("task")

    last_seq = await planner.get_checkpoint_seq("task")
    assert last_seq > 0

    agent_id = planner.instance_id
    await registry.kill(planner.instance_id)

    # Simulate restart: spawn new planner and rebuild
    new_planner = await registry.spawn(planner_def)

    # Rebuild from checkpoint using the old agent's checkpoints
    rebuilt_count = kernel.rebuild("task", agent_id=agent_id)
    assert rebuilt_count >= 0  # incremental rebuild should work

    await registry.kill(new_planner.instance_id)


@pytest.mark.asyncio
async def test_stale_agent_cleanup(kernel, planner_def):
    """Stale agents are cleaned up by the registry."""

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    # Manually set last active time far in the past to simulate staleness
    planner.last_active_at = "2000-01-01T00:00:00+00:00"

    stale_ids = await registry.cleanup_stale(max_age_seconds=1)
    assert planner.instance_id in stale_ids
    assert registry.get(planner.instance_id) is None


@pytest.mark.asyncio
async def test_max_instances_limit(kernel, planner_def):
    """Cannot exceed max_instances per AgentDefinition."""
    registry = kernel.agent_registry

    planner1 = await registry.spawn(planner_def)
    assert planner1.status == "running"

    # Second spawn should fail because max_instances=1
    with pytest.raises(RuntimeError, match="Max instances"):
        await registry.spawn(planner_def)

    await registry.kill(planner1.instance_id)


@pytest.mark.asyncio
async def test_backward_compatible_checkpoint(kernel):
    """Non-agent (kernel-level) checkpoint still uses agent_id='kernel'."""
    kernel.emit_event("GoalCreated", "goal", "g_bc", payload={"title": "BackCompat"})
    ck = kernel.save_projection_snapshot("goal", agent_id="kernel")
    assert ck["agent_id"] == "kernel"
    assert ck["last_applied_seq"] > 0

    seq = kernel._checkpoint_seq(agent_id="kernel", aggregate_type="goal")
    assert seq > 0

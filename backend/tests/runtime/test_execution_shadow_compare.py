"""ADR-0007 Step 2 — shadow compare: persist_work_item vs Execution projection."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_runtime():
    from app.core.runtime.agent_scheduler import reset_scheduler
    from app.core.runtime.execution_shadow_compare import reset_shadow_compare_stats

    reset_scheduler()
    reset_shadow_compare_stats()
    yield
    reset_scheduler()
    reset_shadow_compare_stats()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "shadow_compare.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

    return AgentDefinition(
        agent_id="shadow_planner",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )



@pytest.mark.asyncio
async def test_shadow_compare_success_path_zero_mismatches(kernel, planner_def):
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_shadow_compare import (
        assert_zero_mismatches,
        get_shadow_compare_stats,
        verify_stored_matches_event_replay,
    )
    from app.core.runtime.handler_registry import _registry, subscribe

    @subscribe("ShadowSuccess")
    async def on_success(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "ShadowSuccess", "task", "task_shadow_ok", payload={}, actor="user",
    )
    item = scheduler.enqueue(planner.instance_id, planner.actor_id(), event)
    await scheduler.flush()
    await scheduler.stop()

    verify_stored_matches_event_replay(kernel, item.id)
    stats = get_shadow_compare_stats()
    assert stats.checkpoints_checked > 0
    assert_zero_mismatches(stats)

    _registry.pop("ShadowSuccess", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_shadow_compare_retry_path_zero_mismatches(kernel, planner_def):
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_shadow_compare import (
        assert_zero_mismatches,
        get_shadow_compare_stats,
        verify_stored_matches_event_replay,
    )
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.work_item import ExecutionPolicy

    call_count = 0

    @subscribe("ShadowRetry")
    async def on_retry(instance, event):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient")

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "ShadowRetry", "task", "task_shadow_retry", payload={}, actor="user",
    )

    item = scheduler.enqueue(
        planner.instance_id,
        planner.actor_id(),
        event,
        policy=ExecutionPolicy(max_retries=3, retry_delay_seconds=0.05),
    )
    await scheduler.flush()
    await asyncio.sleep(0.15)
    await scheduler.flush()
    await scheduler.stop()

    assert call_count >= 3
    verify_stored_matches_event_replay(kernel, item.id)
    stats = get_shadow_compare_stats()
    assert stats.checkpoints_checked >= 5
    assert_zero_mismatches(stats)

    _registry.pop("ShadowRetry", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_shadow_compare_terminal_failure_zero_mismatches(kernel, planner_def):
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_shadow_compare import (
        assert_zero_mismatches,
        verify_stored_matches_event_replay,
    )
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.work_item import ExecutionPolicy

    @subscribe("ShadowFail")
    async def on_fail(instance, event):
        raise RuntimeError("permanent")

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "ShadowFail", "task", "task_shadow_fail", payload={}, actor="user",
    )
    item = scheduler.enqueue(
        planner.instance_id,
        planner.actor_id(),
        event,
        policy=ExecutionPolicy(max_retries=0, retry_delay_seconds=0.01),
    )
    await scheduler.flush()
    await scheduler.stop()

    rows = kernel.read_work_items(status="failed")
    assert any(w.id == item.id for w in rows)

    verify_stored_matches_event_replay(kernel, item.id)
    assert_zero_mismatches()

    _registry.pop("ShadowFail", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_shadow_compare_batch_n_executions_zero_mismatches(kernel, planner_def):
    """N scheduler executions, 0 mismatches across all checkpoints."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_shadow_compare import (
        assert_zero_mismatches,
        get_shadow_compare_stats,
        verify_stored_matches_event_replay,
    )
    from app.core.runtime.handler_registry import _registry, subscribe

    execution_ids: list[str] = []

    for i in range(5):
        event_type = f"ShadowBatch{i}"

        @subscribe(event_type)
        async def on_batch(instance, event, _i=i):
            if _i % 2 == 1:
                raise RuntimeError("fail")

        registry = kernel.agent_registry
        planner = await registry.spawn(planner_def)
        scheduler = get_scheduler(kernel)
        await scheduler.start()

        event = kernel.emit_event(
            event_type, "task", f"task_batch_{i}", payload={}, actor="user",
        )
        from app.core.runtime.work_item import ExecutionPolicy

        policy = (
            ExecutionPolicy(max_retries=0, retry_delay_seconds=0.01)
            if i % 2 == 1
            else None
        )
        item = scheduler.enqueue(planner.instance_id, planner.actor_id(), event, policy=policy)
        await scheduler.flush()
        await scheduler.stop()
        execution_ids.append(item.id)
        _registry.pop(event_type, None)
        await registry.kill(planner.instance_id)

    stats = get_shadow_compare_stats()
    for eid in execution_ids:
        verify_stored_matches_event_replay(kernel, eid)

    assert stats.executions_checked == len(execution_ids)
    assert stats.mismatches == 0
    assert_zero_mismatches(stats)

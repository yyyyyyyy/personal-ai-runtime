"""Tests for Execution Model — WorkItem state machine and Scheduler.

Validates:
    - WorkItem transitions: pending → running → completed
    - WorkItem retry: pending → running → failed → retrying → pending
    - Scheduler enqueue/dequeue
    - WorkItem persistence (handler_executions table)
    - Scheduler recovery after restart
"""

import asyncio
import os
import time

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the global scheduler singleton between tests."""
    from app.core.runtime.agent_scheduler import reset_scheduler
    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "exec.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule
    return AgentDefinition(
        agent_id="exec_planner",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


def test_work_item_state_machine():
    """WorkItem transitions through pending → running → completed."""
    from app.core.runtime.work_item import WorkItem

    item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_task_created",
        instance_id="test_instance",
    )
    assert item.status == "pending"
    assert item.retry_count == 0

    item.transition_to("running")
    assert item.status == "running"
    assert item.started_at is not None

    item.transition_to("completed")
    assert item.status == "completed"
    assert item.completed_at is not None


def test_work_item_retry_limits():
    """WorkItem respects max_retries and can_retry checks."""
    from app.core.runtime.work_item import ExecutionPolicy, WorkItem

    policy = ExecutionPolicy(max_retries=2, retry_delay_seconds=0.1)
    item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_task_created",
        instance_id="test",
        policy=policy,
    )

    assert item.can_retry() is True
    item.retry_count = 1
    assert item.can_retry() is True
    item.retry_count = 2
    assert item.can_retry() is False


def test_work_item_persistence(kernel, planner_def):
    """WorkItem projection is created from Execution events."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.work_item import WorkItem

    item = WorkItem(
        event_seq=1,
        event_id="evt_test",
        event_type="TaskCreated",
        handler_name="on_task_created",
        instance_id="test_instance",
        status="pending",
        correlation_id="corr_123",
    )
    # ADR-0007 Step 10: use event emission (triggers projector) instead of
    # persist_work_item which has been removed from Kernel.
    kernel.emit_event(
        "ExecutionRequested",
        AGGREGATE_EXECUTION,
        item.id,
        payload={
            "execution_id": item.id,
            "actor": "agent:test_instance",
            "handler_name": item.handler_name,
            "trigger_event_id": item.event_id,
            "trigger_event_seq": item.event_seq,
            "trigger_event_type": item.event_type,
            "instance_id": item.instance_id,
            "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
            "correlation_id": item.correlation_id,
            "created_at": item.created_at,
            "event_seq": item.event_seq,
        },
        actor="scheduler",
    )

    items = kernel.read_work_items(status="pending")
    assert len(items) >= 1

    found = [w for w in items if w.id == item.id]
    assert len(found) == 1
    assert found[0].event_type == "TaskCreated"
    assert found[0].status == "pending"


def test_work_item_update_status(kernel):
    """WorkItem status transitions through Execution events."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.work_item import WorkItem

    item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="test",
        status="running",
    )
    eid = item.id
    # Create via ExecutionRequested + ExecutionStarted
    kernel.emit_event("ExecutionRequested", AGGREGATE_EXECUTION, eid, payload={
        "execution_id": eid, "actor": "agent:test",
        "handler_name": "on_test", "trigger_event_id": "evt_test",
        "trigger_event_seq": 0, "trigger_event_type": "TaskCreated",
        "instance_id": "test", "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
        "correlation_id": "", "created_at": item.created_at, "event_seq": 0,
    }, actor="scheduler")
    kernel.emit_event("ExecutionStarted", AGGREGATE_EXECUTION, eid, payload={
        "execution_id": eid, "attempt": 1, "started_at": item.started_at or "",
    }, actor="scheduler")

    item.transition_to("completed")
    kernel.emit_event("ExecutionCompleted", AGGREGATE_EXECUTION, eid, payload={
        "execution_id": eid, "completed_at": item.completed_at or "",
    }, actor="scheduler")

    items = kernel.read_work_items(status="completed")
    assert any(w.id == item.id for w in items)


@pytest.mark.asyncio
async def test_scheduler_enqueue_and_process(kernel, planner_def):
    """Scheduler enqueues a WorkItem and processes it."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe

    received = []

    @subscribe("SchedulerEnqueueTest")
    async def on_enqueue_test(instance, event):
        received.append(event)

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "SchedulerEnqueueTest", "task", "task_exec_1",
        payload={"name": "test"},
        actor="user",
    )
    scheduler.enqueue(planner.instance_id, planner.actor_id(), event)

    await scheduler.flush()
    await scheduler.stop()

    assert len(received) >= 1
    assert received[0].type == "SchedulerEnqueueTest"

    _registry.pop("SchedulerEnqueueTest", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_scheduler_work_item_completes(kernel, planner_def):
    """A WorkItem transitions to completed after handler success."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe

    executed = []

    @subscribe("SchedulerCompleteTest")
    async def on_complete_test(instance, event):
        executed.append("ok")

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "SchedulerCompleteTest", "task", "task_exec_2",
        payload={}, actor="user",
    )
    scheduler.enqueue(planner.instance_id, planner.actor_id(), event)

    await scheduler.flush()

    completed = kernel.read_work_items(status="completed")
    assert len(completed) >= 1
    assert len(executed) >= 1

    _registry.pop("SchedulerCompleteTest", None)
    await scheduler.stop()
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_scheduler_retries_failed_item(kernel, planner_def):
    """A failing handler is retried up to max_retries."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe

    # Use a unique event type to avoid registry collisions with other tests
    handler_event_type = "TaskRetryTest"

    call_count = 0

    @subscribe(handler_event_type)
    async def retry_test_handler(instance, event):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient error")

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        handler_event_type, "task", "task_retry",
        payload={}, actor="user",
    )
    from app.core.runtime.work_item import ExecutionPolicy

    scheduler.enqueue(
        planner.instance_id,
        planner.actor_id(),
        event,
        policy=ExecutionPolicy(max_retries=3, retry_delay_seconds=0.05),
    )
    deadline = time.monotonic() + 3.0
    while call_count < 3 and time.monotonic() < deadline:
        await scheduler.flush()
        await asyncio.sleep(0.05)

    assert call_count >= 3

    completed = kernel.read_work_items(status="completed")
    assert len(completed) >= 1

    # Clean up the handler to avoid polluting other tests
    _registry.pop(handler_event_type, None)

    await scheduler.stop()
    await registry.kill(planner.instance_id)


def test_recover_work_items_scans_without_mutating(kernel):
    """recover_work_items scans running/pending rows but performs NO writes.

    ADR-0007 Step 3: recovery no longer issues a bare UPDATE. The running →
    retrying transition is driven by the Scheduler via ExecutionRetried
    events. This test pins the scanner contract: the call returns a
    (running, pending) tuple and leaves handler_executions untouched.
    """
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.work_item import WorkItem

    running_item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="test",
        status="running",
    )
    pending_item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="test",
        status="pending",
    )
    # ADR-0007 Step 10: use events instead of persist_work_item
    for it in (running_item, pending_item):
        kernel.emit_event("ExecutionRequested", AGGREGATE_EXECUTION, it.id, payload={
            "execution_id": it.id, "actor": "agent:test",
            "handler_name": it.handler_name, "trigger_event_id": "evt_test",
            "trigger_event_seq": 0, "trigger_event_type": it.event_type,
            "instance_id": it.instance_id,
            "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
            "correlation_id": it.correlation_id, "created_at": it.created_at,
            "event_seq": 0,
        }, actor="scheduler")
        if it.status == "running":
            kernel.emit_event("ExecutionStarted", AGGREGATE_EXECUTION, it.id, payload={
                "execution_id": it.id, "attempt": 1, "started_at": it.started_at or "",
            }, actor="scheduler")

    running, pending = kernel.recover_work_items()

    # running bucket contains the interrupted item, still 'running' — caller
    # is responsible for transitioning it via events.
    assert any(w.id == running_item.id for w in running)
    assert all(w.status == "running" for w in running)

    # pending bucket contains pending/retrying items, ready to re-enqueue.
    assert any(w.id == pending_item.id for w in pending)

    # Scanner must not mutate: the running row stays 'running' in the table
    # until the Scheduler emits ExecutionRetried.
    rows = kernel.read_work_items(status="running")
    assert any(w.id == running_item.id for w in rows)


def test_work_item_to_row_roundtrip(kernel):
    """WorkItem.to_row() and from_row() are symmetric."""
    from app.core.runtime.work_item import ExecutionPolicy, WorkItem

    policy = ExecutionPolicy(timeout_seconds=10.0, max_retries=5, retry_delay_seconds=2.0)
    original = WorkItem(
        event_seq=42,
        event_id="evt_abc",
        event_type="TaskPlanned",
        handler_name="on_task_planned",
        instance_id="inst_xyz",
        status="running",
        retry_count=1,
        policy=policy,
        correlation_id="corr_abc",
    )
    original.transition_to("running")
    original.transition_to("completed")

    row = original.to_row()
    restored = WorkItem.from_row(row)

    assert restored.id == original.id
    assert restored.event_type == original.event_type
    assert restored.handler_name == original.handler_name
    assert restored.status == "completed"
    assert restored.retry_count == original.retry_count
    assert restored.policy.timeout_seconds == policy.timeout_seconds
    assert restored.policy.max_retries == policy.max_retries

"""Tests for Execution Model — WorkItem state machine and Scheduler.

Validates:
    - WorkItem transitions: pending → running → completed
    - WorkItem retry: pending → running → failed → retrying → pending
    - Scheduler enqueue/dequeue
    - WorkItem persistence (handler_executions table)
    - Scheduler recovery after restart
"""

import pytest

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


def test_work_item_state_machine():
    """WorkItem transitions through pending → running → completed."""
    from app.core.runtime.scheduled_execution import ScheduledExecution

    item = ScheduledExecution(
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
    from app.core.runtime.scheduled_execution import ExecutionPolicy, ScheduledExecution

    policy = ExecutionPolicy(max_retries=2, retry_delay_seconds=0.1)
    item = ScheduledExecution(
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


def test_work_item_update_status(kernel):
    """WorkItem status transitions through Execution events."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.scheduled_execution import ScheduledExecution

    item = ScheduledExecution(
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

    items = kernel.read_scheduled_executions(status="completed")
    assert any(w.id == item.id for w in items)


def test_count_scheduled_executions_by_status(kernel):
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

    for status, eid in (("pending", "ex-p"), ("running", "ex-r"), ("completed", "ex-c")):
        kernel.emit_event(
            "ExecutionRequested",
            AGGREGATE_EXECUTION,
            eid,
            payload={
                "execution_id": eid,
                "actor": "agent:test",
                "handler_name": "on_test",
                "trigger_event_id": "evt",
                "trigger_event_seq": 0,
                "trigger_event_type": "TaskCreated",
                "instance_id": "test",
                "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
                "correlation_id": None,
                "created_at": "2026-01-01T00:00:00Z",
                "event_seq": 0,
            },
            actor="scheduler",
        )
        if status == "running":
            kernel.emit_event(
                "ExecutionStarted",
                AGGREGATE_EXECUTION,
                eid,
                payload={"execution_id": eid, "attempt": 1, "started_at": "2026-01-01T00:00:01Z"},
                actor="scheduler",
            )
        elif status == "completed":
            kernel.emit_event(
                "ExecutionStarted",
                AGGREGATE_EXECUTION,
                eid,
                payload={"execution_id": eid, "attempt": 1, "started_at": "2026-01-01T00:00:01Z"},
                actor="scheduler",
            )
            kernel.emit_event(
                "ExecutionCompleted",
                AGGREGATE_EXECUTION,
                eid,
                payload={"execution_id": eid, "completed_at": "2026-01-01T00:00:02Z"},
                actor="scheduler",
            )

    counts = kernel.count_scheduled_executions_by_status()
    assert counts.get("pending") == 1
    assert counts.get("running") == 1
    assert counts.get("completed") == 1


def test_recover_work_items_scans_without_mutating(kernel):
    """recover_scheduled_executions scans running/pending rows but performs NO writes.

    Execution 契约 §3: recovery does not issue a bare UPDATE. The running →
    retrying transition is driven by the Scheduler via ExecutionRetried
    events. This test pins the scanner contract: the call returns a
    (running, pending) tuple and leaves handler_executions untouched.
    """
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.scheduled_execution import ScheduledExecution

    running_item = ScheduledExecution(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="test",
        status="running",
    )
    pending_item = ScheduledExecution(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="test",
        status="pending",
    )
    # Use events instead of persist_work_item
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

    running, pending = kernel.recover_scheduled_executions()

    # running bucket contains the interrupted item, still 'running' — caller
    # is responsible for transitioning it via events.
    assert any(w.id == running_item.id for w in running)
    assert all(w.status == "running" for w in running)

    # pending bucket contains pending/retrying items, ready to re-enqueue.
    assert any(w.id == pending_item.id for w in pending)

    # Scanner must not mutate: the running row stays 'running' in the table
    # until the Scheduler emits ExecutionRetried.
    rows = kernel.read_scheduled_executions(status="running")
    assert any(w.id == running_item.id for w in rows)


def test_work_item_to_row_roundtrip(kernel):
    """WorkItem.to_row() and from_row() are symmetric."""
    from app.core.runtime.scheduled_execution import ExecutionPolicy, ScheduledExecution

    policy = ExecutionPolicy(timeout_seconds=10.0, max_retries=5, retry_delay_seconds=2.0)
    original = ScheduledExecution(
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
    # status is already running; transition straight to completed (the
    # no-op running->running is rejected by StateManager validation).
    original.transition_to("completed")

    row = original.to_row()
    restored = ScheduledExecution.from_row(row)

    assert restored.id == original.id
    assert restored.event_type == original.event_type
    assert restored.handler_name == original.handler_name
    assert restored.status == "completed"
    assert restored.retry_count == original.retry_count
    assert restored.policy.timeout_seconds == policy.timeout_seconds
    assert restored.policy.max_retries == policy.max_retries

"""ADR-0007 Step 3 — event-driven recovery.

Recovery mutates handler_executions only through Execution events. The
running → retrying transition that previously happened via a bare UPDATE
is now driven by ExecutionRetried(reason='interrupted') emitted through
the same _persist_emit_verify path as the scheduler hot path.
"""

from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_runtime():
    from app.core.runtime.agent_scheduler import reset_scheduler
    from app.core.runtime.execution_shadow_compare import (
        reset_shadow_compare_stats,
    )

    reset_scheduler()
    reset_shadow_compare_stats()
    yield
    reset_scheduler()
    reset_shadow_compare_stats()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "recovery.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

    return AgentDefinition(
        agent_id="recovery_planner",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


# ── Anti-pattern guard: recovery must not contain a bare UPDATE ─────────


def test_recovery_no_direct_sql_mutation():
    """recover_work_items must not mutate handler_executions via bare SQL.

    A 'fake Step 3' keeps the legacy UPDATE alongside the new emit path so
    that shadow compare passes trivially while bare SQL remains the truth
    source. This source-level guard blocks that regression: the function
    body must contain no UPDATE against handler_executions.
    """
    from app.core.runtime.kernel.kernel import Kernel

    src = inspect.getsource(Kernel.recover_work_items)
    assert "UPDATE handler_executions" not in src, (
        "ADR-0007 Step 3 violation: recover_work_items still mutates via bare "
        "SQL. Recovery must go through ExecutionRetried event emission only."
    )


# ── Scanner contract: recover_work_items returns (running, pending) ─────


def test_recover_work_items_returns_running_and_pending_buckets(kernel):
    """recover_work_items returns interrupted ('running') items separately
    from already-pending items, without mutating either."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.work_item import WorkItem

    running_item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="inst_a",
        status="running",
    )
    pending_item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_test",
        instance_id="inst_b",
        status="pending",
    )
    # Step 10: use event emission instead of persist_work_item
    for it in (running_item, pending_item):
        kernel.emit_event("ExecutionRequested", AGGREGATE_EXECUTION, it.id, payload={
            "execution_id": it.id, "actor": f"agent:{it.instance_id}",
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

    assert any(w.id == running_item.id for w in running)
    assert all(w.status == "running" for w in running)
    assert any(w.id == pending_item.id for w in pending)

    # No mutation: the 'running' row is still 'running' until the Scheduler
    # emits ExecutionRetried.
    still_running = kernel.read_work_items(status="running")
    assert any(w.id == running_item.id for w in still_running)


# ── Crash / restart parity: full Operational Proof from ADR Step 3 ──────


@pytest.mark.asyncio
async def test_recovery_emits_execution_retried_for_interrupted(kernel, planner_def):
    """Simulated crash leaves an execution 'running'; a fresh scheduler
    instance must recover it by emitting ExecutionRetried(reason=interrupted),
    not by mutating the row in place."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.execution_shadow_compare import (
        assert_zero_mismatches,
        get_shadow_compare_stats,
    )
    from app.core.runtime.handler_registry import _registry, subscribe

    @subscribe("RecoveryInterrupt")
    async def on_interrupt(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    # Phase 1: run the scheduler, enqueue, get the item to 'running', then
    # simulate a crash by stopping before it completes. We do this by
    # enqueueing but NOT flushing — the item stays 'pending' in the table
    # at this point, so we instead directly construct a 'running' row to
    # emulate a mid-flight crash snapshot.
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    trigger = kernel.emit_event(
        "RecoveryInterrupt", "task", "task_recovery_1", payload={}, actor="user",
    )
    enqueued = scheduler.enqueue(planner.instance_id, planner.actor_id(), trigger)
    await scheduler.stop()

    # Force the row into 'running' to emulate a crash mid-execution. We
    # replay the scheduler's own hot-path emissions (ExecutionStarted) so the
    # event stream reflects what really happened before the crash, then leave
    # the item 'running' without a terminal event — exactly the interrupted
    # state recovery must handle.
    from app.core.runtime.execution_events import emit_execution_started
    enqueued.transition_to("running")
    emit_execution_started(kernel, enqueued)

    # Phase 2: new scheduler instance boots and recovers. Scheduler is a
    # singleton keyed on kernel; reset to force reconstruction.
    from app.core.runtime.agent_scheduler import reset_scheduler
    reset_scheduler()
    scheduler2 = get_scheduler(kernel)

    # Recovery runs in __init__, so by the time we have scheduler2 the
    # ExecutionRetried events must already be in the log.
    events = kernel.read_events(aggregate_type="execution")
    retried = [
        e for e in events
        if e.type == "ExecutionRetried"
        and e.payload.get("reason") == "interrupted"
        and e.aggregate_id == enqueued.id
    ]
    assert retried, (
        "Expected ExecutionRetried(reason=interrupted) in event_log after "
        "recovery; recovery did not emit events for the interrupted item."
    )

    # The row in handler_executions must now be 'pending' (re-enqueued).
    rows = kernel.read_work_items()
    row = next(w for w in rows if w.id == enqueued.id)
    assert row.status == "pending", (
        f"Recovered row should be 'pending' (re-enqueued); got {row.status!r}"
    )

    # Shadow compare must hold across the recovery path.
    stats = get_shadow_compare_stats()
    assert stats.mismatches == 0, (
        f"Shadow compare drift on recovery path: {stats.mismatches} mismatch(es)"
    )
    assert_zero_mismatches(stats)

    _registry.pop("RecoveryInterrupt", None)
    await scheduler2.stop()
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_recovery_rebuild_matches_handler_executions(kernel, planner_def):
    """After a crash/recover cycle, rebuild('execution') reconstructs the
    same handler_executions snapshot — proving the event stream is now
    complete and self-sufficient, including recovery transitions."""
    from app.core.runtime.agent_scheduler import get_scheduler, reset_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

    @subscribe("RecoveryRebuild")
    async def on_rebuild(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    trigger = kernel.emit_event(
        "RecoveryRebuild", "task", "task_recovery_rebuild", payload={}, actor="user",
    )
    enqueued = scheduler.enqueue(planner.instance_id, planner.actor_id(), trigger)
    await scheduler.stop()

    # Emulate mid-flight crash: emit ExecutionStarted (as the scheduler would
    # have) then leave the item 'running' with no terminal event.
    from app.core.runtime.execution_events import emit_execution_started
    enqueued.transition_to("running")
    emit_execution_started(kernel, enqueued)

    # Recover via a fresh scheduler instance.
    reset_scheduler()
    get_scheduler(kernel)

    # Snapshot the projection.
    with kernel._db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM handler_executions ORDER BY id"
        ).fetchall()
    before = [dict(r) for r in rows]

    # Wipe and rebuild purely from events.
    with kernel._db.get_db() as conn:
        conn.execute("DELETE FROM handler_executions")
    kernel.rebuild(AGGREGATE_EXECUTION)

    with kernel._db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM handler_executions ORDER BY id"
        ).fetchall()
    after = [dict(r) for r in rows]

    assert before == after, (
        "rebuild('execution') did not reproduce handler_executions after "
        "recovery; the event stream is incomplete."
    )

    _registry.pop("RecoveryRebuild", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_recovery_re_enqueued_set_matches_legacy_semantics(kernel, planner_def):
    """Behavior parity: the set of items re-enqueued after recovery matches
    what the legacy recover_work_items (which returned pending+retrying)
    would have produced — i.e. no item is dropped or duplicated."""
    from app.core.runtime.agent_scheduler import get_scheduler, reset_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION
    from app.core.runtime.work_item import WorkItem

    @subscribe("RecoveryParity")
    async def on_parity(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)

    # Seed three rows directly: one running (interrupted), two pending.
    running_item = WorkItem(
        event_type="TaskCreated",
        handler_name="on_parity",
        instance_id=planner.instance_id,
        status="running",
    )
    pending_a = WorkItem(
        event_type="TaskCreated",
        handler_name="on_parity",
        instance_id=planner.instance_id,
        status="pending",
    )
    pending_b = WorkItem(
        event_type="TaskCreated",
        handler_name="on_parity",
        instance_id=planner.instance_id,
        status="pending",
    )
    for it in (running_item, pending_a, pending_b):
        # Step 10: emit events instead of persist_work_item
        kernel.emit_event("ExecutionRequested", AGGREGATE_EXECUTION, it.id, payload={
            "execution_id": it.id, "actor": f"agent:{planner.instance_id}",
            "handler_name": it.handler_name, "trigger_event_id": "evt_parity",
            "trigger_event_seq": 0, "trigger_event_type": it.event_type,
            "instance_id": it.instance_id,
            "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
            "correlation_id": it.correlation_id, "created_at": it.created_at,
            "event_seq": 0,
        }, actor="scheduler")
        if it.status == "running":
            it.started_at = it.started_at or ""
            kernel.emit_event("ExecutionStarted", AGGREGATE_EXECUTION, it.id, payload={
                "execution_id": it.id, "attempt": 1, "started_at": it.started_at,
            }, actor="scheduler")

    # New scheduler recovers.
    reset_scheduler()
    scheduler = get_scheduler(kernel)

    # All three must be in the pending queue.
    enqueued_ids = {w.id for w in scheduler._pending}
    expected = {running_item.id, pending_a.id, pending_b.id}
    assert enqueued_ids == expected, (
        f"Recovery re-enqueued {enqueued_ids}; expected {expected}"
    )

    _registry.pop("RecoveryParity", None)
    await scheduler.stop()
    await registry.kill(planner.instance_id)

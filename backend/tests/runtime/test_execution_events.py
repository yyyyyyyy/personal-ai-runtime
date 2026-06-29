"""ADR-0007 Step 1 — Execution event stream and projection tests."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler

    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "execution_events.db")))


@pytest.fixture
def planner_def():
    from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

    return AgentDefinition(
        agent_id="exec_planner",
        subscriptions=[SubscriptionRule(event_type="TaskCreated")],
    )


def _snapshot_handler_executions(db) -> list[dict]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM handler_executions ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def _normalize_row(row: dict) -> dict:
    out = dict(row)
    if out.get("policy_json"):
        out["policy_json"] = json.dumps(
            json.loads(out["policy_json"]), sort_keys=True,
        )
    return out


def _assert_rows_equal(before: list[dict], after: list[dict]) -> None:
    assert len(before) == len(after)
    for left, right in zip(
        [_normalize_row(r) for r in before],
        [_normalize_row(r) for r in after],
    ):
        assert left == right


@pytest.mark.asyncio
async def test_execution_events_emitted_by_scheduler(kernel, planner_def):
    """Scheduler dual-write emits Execution lifecycle events into event_log."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.kernel.constants import EXECUTION_EVENT_TYPES

    @subscribe("ExecEventLogTest")
    async def on_test(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "ExecEventLogTest", "task", "task_evt_1", payload={}, actor="user",
    )
    item = scheduler.enqueue(planner.instance_id, planner.actor_id(), event)
    await scheduler.flush()
    await scheduler.stop()

    types = {
        e.type
        for e in kernel.read_events(aggregate_type="execution")
    }
    assert "ExecutionRequested" in types
    assert "ExecutionStarted" in types
    assert "ExecutionCompleted" in types
    assert types <= EXECUTION_EVENT_TYPES | {"ExecutionRequested", "ExecutionStarted", "ExecutionCompleted"}
    assert "ExecutionCreated" not in types
    assert item is not None

    _registry.pop("ExecEventLogTest", None)
    await registry.kill(planner.instance_id)


@pytest.mark.asyncio
async def test_rebuild_execution_matches_handler_executions(kernel, planner_def):
    """Execution aggregate reconstructs handler_executions from the event log."""
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import _registry, subscribe
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

    @subscribe("RebuildIdentityTest")
    async def on_rebuild(instance, event):
        pass

    registry = kernel.agent_registry
    planner = await registry.spawn(planner_def)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    event = kernel.emit_event(
        "RebuildIdentityTest", "task", "task_rebuild_1", payload={}, actor="user",
    )
    scheduler.enqueue(planner.instance_id, planner.actor_id(), event)
    await scheduler.flush()
    await scheduler.stop()

    before = _snapshot_handler_executions(kernel._db)
    assert before, "expected handler_executions rows after scheduler run"

    with kernel._db.get_db() as conn:
        conn.execute("DELETE FROM handler_executions")

    replayed = kernel.rebuild(AGGREGATE_EXECUTION)
    assert replayed > 0

    after = _snapshot_handler_executions(kernel._db)
    _assert_rows_equal(before, after)

    _registry.pop("RebuildIdentityTest", None)
    await registry.kill(planner.instance_id)


def test_rebuild_execution_after_retry_event_sequence(kernel):
    """Retry lifecycle event sequence rebuilds to the same handler_executions snapshot."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

    eid = "wi_retry_rebuild"
    base = {
        "execution_id": eid,
        "actor": "agent:test",
        "handler_name": "on_retry",
        "trigger_event_id": "evt_r",
        "trigger_event_seq": 10,
        "trigger_event_type": "TaskRetryTest",
        "instance_id": "aginst_retry",
        "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
        "correlation_id": "corr_retry",
        "created_at": "2026-01-01T00:00:00+00:00",
        "event_seq": 10,
    }
    kernel.emit_event("ExecutionRequested", AGGREGATE_EXECUTION, eid, payload=base, actor="scheduler")
    kernel.emit_event(
        "ExecutionStarted", AGGREGATE_EXECUTION, eid,
        payload={"execution_id": eid, "attempt": 1, "started_at": "2026-01-01T00:00:01+00:00"},
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionRetried", AGGREGATE_EXECUTION, eid,
        payload={"execution_id": eid, "attempt": 1, "reason": "transient", "status": "retrying"},
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionRetried", AGGREGATE_EXECUTION, eid,
        payload={"execution_id": eid, "attempt": 1, "reason": "transient", "status": "pending"},
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionStarted", AGGREGATE_EXECUTION, eid,
        payload={"execution_id": eid, "attempt": 2, "started_at": "2026-01-01T00:00:06+00:00"},
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionCompleted", AGGREGATE_EXECUTION, eid,
        payload={"execution_id": eid, "completed_at": "2026-01-01T00:00:07+00:00", "result_summary": ""},
        actor="scheduler",
    )

    before = _snapshot_handler_executions(kernel._db)
    with kernel._db.get_db() as conn:
        conn.execute("DELETE FROM handler_executions")

    kernel.rebuild(AGGREGATE_EXECUTION)
    after = _snapshot_handler_executions(kernel._db)
    _assert_rows_equal(before, after)


def test_execution_paused_resumed_cancelled_projectors(kernel):
    """Paused / Resumed / Cancelled events project to handler_executions."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION

    eid = "wi_projector_manual"
    kernel.emit_event(
        "ExecutionRequested",
        AGGREGATE_EXECUTION,
        eid,
        payload={
            "execution_id": eid,
            "actor": "agent:test",
            "handler_name": "on_test",
            "trigger_event_id": "evt_1",
            "trigger_event_seq": 1,
            "trigger_event_type": "TaskCreated",
            "instance_id": "aginst_test",
            "policy": {"timeout": 30.0, "max_retries": 3, "retry_delay": 5.0},
            "correlation_id": "corr",
            "created_at": "2026-01-01T00:00:00+00:00",
            "event_seq": 1,
        },
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionStarted",
        AGGREGATE_EXECUTION,
        eid,
        payload={"execution_id": eid, "attempt": 1, "started_at": "2026-01-01T00:00:01+00:00"},
        actor="scheduler",
    )
    kernel.emit_event(
        "ExecutionPaused",
        AGGREGATE_EXECUTION,
        eid,
        payload={"execution_id": eid, "reason": "backpressure", "paused_at": "2026-01-01T00:00:02+00:00"},
        actor="scheduler",
    )
    rows = kernel.read_work_items()
    row = next(w for w in rows if w.id == eid)
    assert row.status == "paused"

    kernel.emit_event(
        "ExecutionResumed",
        AGGREGATE_EXECUTION,
        eid,
        payload={"execution_id": eid, "resumed_at": "2026-01-01T00:00:03+00:00"},
        actor="scheduler",
    )
    row = next(w for w in kernel.read_work_items() if w.id == eid)
    assert row.status == "pending"

    kernel.emit_event(
        "ExecutionCancelled",
        AGGREGATE_EXECUTION,
        eid,
        payload={"execution_id": eid, "reason": "superseded", "cancelled_at": "2026-01-01T00:00:04+00:00"},
        actor="scheduler",
    )
    row = next(w for w in kernel.read_work_items() if w.id == eid)
    assert row.status == "cancelled"

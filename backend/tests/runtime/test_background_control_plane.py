"""Background work-item recovery + cooperative cancellation (INV-W5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.runtime.execution import (
    clear_all_cancels,
    is_execution_cancelled,
)
from app.core.runtime.execution_events import emit_execution_requested
from app.core.runtime.handlers.plan_runner import run_plan_steps
from app.core.runtime.kernel.constants import (
    AGGREGATE_WORK_ITEM,
    EVENT_WORK_ITEM_CREATED,
    EVENT_WORK_ITEM_STATUS_CHANGED,
)
from app.core.runtime.kernel.event import Event
from app.core.runtime.scheduled_execution import ScheduledExecution


@pytest.fixture(autouse=True)
def _reset_cancels_and_scheduler():
    from app.core.runtime.agent_scheduler import reset_scheduler

    clear_all_cancels()
    reset_scheduler()
    yield
    clear_all_cancels()
    reset_scheduler()


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "bg_ctl.db")))


def _create_running(kernel, work_id: str = "t1") -> None:
    kernel.emit_event(
        EVENT_WORK_ITEM_CREATED,
        AGGREGATE_WORK_ITEM,
        work_id,
        payload={
            "title": "x",
            "description": "",
            "work_type": "background",
            "parent_work_id": None,
            "parent_goal_id": None,
            "status": "pending",
            "priority": 0,
            "executable_plan": "{}",
            "progress": 0.0,
            "created_at": "2026-01-01T00:00:00Z",
        },
        actor="user",
    )
    kernel.emit_event(
        EVENT_WORK_ITEM_STATUS_CHANGED,
        AGGREGATE_WORK_ITEM,
        work_id,
        payload={"status": "running"},
        actor="background",
    )


def test_recover_interrupted_background_tasks_requeues_running(kernel, monkeypatch):
    from app.core.runtime.runtime_loop import RuntimeLoop

    _create_running(kernel, "stuck")
    monkeypatch.setattr("app.core.runtime.runtime_loop.kernel", kernel)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", kernel)
    monkeypatch.setattr(
        "app.core.runtime.read_ports.work.kernel",
        lambda: kernel,
    )

    loop = RuntimeLoop()
    n = loop._recover_interrupted_background_tasks()
    assert n == 1
    rows = kernel.query_state("work_items", id="stuck", limit=1)
    assert rows[0]["status"] == "pending"


def test_recover_skips_waiting_approval(kernel, monkeypatch):
    from app.core.runtime.runtime_loop import RuntimeLoop

    _create_running(kernel, "wa")
    kernel.emit_event(
        EVENT_WORK_ITEM_STATUS_CHANGED,
        AGGREGATE_WORK_ITEM,
        "wa",
        payload={"status": "waiting_approval"},
        actor="background",
    )
    monkeypatch.setattr("app.core.runtime.runtime_loop.kernel", kernel)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", kernel)
    monkeypatch.setattr(
        "app.core.runtime.read_ports.work.kernel",
        lambda: kernel,
    )

    loop = RuntimeLoop()
    assert loop._recover_interrupted_background_tasks() == 0
    rows = kernel.query_state("work_items", id="wa", limit=1)
    assert rows[0]["status"] == "waiting_approval"


@pytest.mark.asyncio
async def test_plan_runner_stops_on_cancel_check():
    mock_kernel = MagicMock()
    mock_kernel.invoke_capability = AsyncMock(
        return_value={"status": "success", "result": "ok"}
    )
    cancelled = {"n": 0}

    def cancel_check() -> bool:
        cancelled["n"] += 1
        return cancelled["n"] >= 1

    outcome = await run_plan_steps(
        steps=[
            {"tool": "t1", "params": {}},
            {"tool": "t2", "params": {}},
        ],
        kernel=mock_kernel,
        actor="background",
        execution_id="ex1",
        correlation_id=None,
        cancel_check=cancel_check,
    )
    assert outcome.stopped_reason == "cancelled"
    mock_kernel.invoke_capability.assert_not_awaited()


def test_scheduler_cancel_executions_for(kernel):
    from app.core.runtime.agent_scheduler import Scheduler

    sch = Scheduler(kernel)
    sch._pending.clear()

    evt = Event(
        type="ExecuteRequested",
        aggregate_type="action",
        aggregate_id="exec_x",
        payload={"action_id": "x"},
        actor="background",
    ).with_seq(1)
    item = ScheduledExecution(
        event_seq=1,
        event_id=evt.id,
        event_type="ExecuteRequested",
        handler_name="on_execute_requested",
        instance_id="runtime:primary",
        _event=evt,
    )
    emit_execution_requested(kernel, item, "background")
    sch._pending.append(item)

    assert sch.cancel_executions_for("x") == 1
    assert all(i.id != item.id for i in sch._pending)
    rows = kernel.read_scheduled_executions(status="failed")
    assert any(r.id == item.id and r.error == "cancelled" for r in rows)


@pytest.mark.asyncio
async def test_cancel_background_task_api(kernel, monkeypatch):
    from app.api import background_tasks as api
    from app.core.runtime.plan_resume import (
        PlanResume,
        configure_plan_resume_db,
        peek_plan_resume,
        register_plan_resume,
    )

    _create_running(kernel, "c1")
    configure_plan_resume_db(kernel._db)
    register_plan_resume(
        "apr_c1",
        PlanResume(kind="execute", resume_from=1, action_id="c1"),
        db=kernel._db,
    )
    monkeypatch.setattr(
        "app.core.runtime.read_ports.work.kernel",
        lambda: kernel,
    )
    monkeypatch.setattr(
        "app.core.runtime.runtime_container.runtime._scheduler",
        None,
    )

    result = await api.cancel_background_task("c1")
    assert result["status"] == "cancelled"
    # Flag stays until a handler acknowledges; durable row is authoritative.
    assert is_execution_cancelled("exec_c1")
    assert peek_plan_resume("apr_c1", db=kernel._db) is None
    configure_plan_resume_db(None)


@pytest.mark.asyncio
async def test_cancel_before_handler_keeps_cancelled_status(kernel, monkeypatch):
    """Cancel arrives before handler acquires the row — status must stay cancelled.

    Regression for the cancel-vs-running race: handler entry previously promoted
    any non-running status to ``running``, clobbering a durable ``cancelled``.
    """
    from app.core.runtime.execution import (
        ExecutionContext,
        request_cancel_execution,
    )
    from app.core.runtime.handlers import execute_handlers as mod
    from app.core.runtime.kernel.event import Event

    _create_running(kernel, "race1")
    # Durable cancel + in-process flag both set (cancel API semantics).
    kernel.emit_event(
        "WorkItemStatusChanged", "work_item", "race1",
        payload={"status": "cancelled"}, actor="user",
    )
    request_cancel_execution("exec_race1")

    evt = Event(
        type="ExecuteRequested",
        aggregate_type="action",
        aggregate_id="exec_race1",
        payload={"action_id": "race1"},
        actor="background",
    ).with_seq(99)
    ctx = ExecutionContext(
        instance_id="runtime:primary",
        actor="background",
        correlation_id="",
        _kernel=kernel,
        execution_id="exec_race1",
    )

    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", kernel)

    await mod.on_execute_requested(ctx, evt)

    rows = kernel.query_state("work_items", id="race1", limit=1)
    assert rows[0]["status"] == "cancelled", (
        "handler must not promote a cancelled row back to running"
    )
    assert not is_execution_cancelled("exec_race1"), "flag must be cleared"

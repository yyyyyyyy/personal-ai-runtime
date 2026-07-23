"""Background task recovery + cooperative cancellation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.runtime.execution import (
    clear_all_cancels,
    is_background_task_cancelled,
)
from app.core.runtime.execution_events import emit_execution_requested
from app.core.runtime.handlers.plan_runner import run_plan_steps
from app.core.runtime.kernel.constants import (
    AGGREGATE_BACKGROUND_TASK,
    EVENT_BG_TASK_CREATED,
    EVENT_BG_TASK_STATUS_CHANGED,
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


def _create_running(kernel, task_id: str = "t1") -> None:
    kernel.emit_event(
        EVENT_BG_TASK_CREATED,
        AGGREGATE_BACKGROUND_TASK,
        f"bg_{task_id}",
        payload={
            "task_id": task_id,
            "user_request": "x",
            "plan_json": "{}",
            "status": "pending",
            "progress": 0.0,
            "created_at": "2026-01-01T00:00:00Z",
        },
        actor="user",
    )
    kernel.emit_event(
        EVENT_BG_TASK_STATUS_CHANGED,
        AGGREGATE_BACKGROUND_TASK,
        f"bg_{task_id}",
        payload={"task_id": task_id, "status": "running", "progress": 0.1},
        actor="background",
    )


def test_recover_interrupted_background_tasks_requeues_running(kernel, monkeypatch):
    from app.core.runtime.runtime_loop import RuntimeLoop

    _create_running(kernel, "stuck")
    monkeypatch.setattr("app.core.runtime.runtime_loop.kernel", kernel)
    monkeypatch.setattr(
        "app.core.runtime.read_ports.query_background_tasks",
        lambda **kw: kernel.query_state("background_tasks", **kw),
    )

    loop = RuntimeLoop()
    n = loop._recover_interrupted_background_tasks()
    assert n == 1
    rows = kernel.query_state("background_tasks", id="stuck", limit=1)
    assert rows[0]["status"] == "pending"


def test_recover_skips_waiting_approval(kernel, monkeypatch):
    from app.core.runtime.runtime_loop import RuntimeLoop

    _create_running(kernel, "wa")
    kernel.emit_event(
        "BackgroundTaskCompleted",
        AGGREGATE_BACKGROUND_TASK,
        "bg_wa",
        payload={"task_id": "wa", "status": "waiting_approval", "progress": 0.2},
        actor="background",
    )
    monkeypatch.setattr("app.core.runtime.runtime_loop.kernel", kernel)
    monkeypatch.setattr(
        "app.core.runtime.read_ports.query_background_tasks",
        lambda **kw: kernel.query_state("background_tasks", **kw),
    )

    loop = RuntimeLoop()
    assert loop._recover_interrupted_background_tasks() == 0
    rows = kernel.query_state("background_tasks", id="wa", limit=1)
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


def test_scheduler_request_cancel_pending(kernel):
    from app.core.runtime.agent_scheduler import Scheduler

    sch = Scheduler(kernel)
    sch._pending.clear()

    evt = Event(
        type="BackgroundTaskRequested",
        aggregate_type="background_task",
        aggregate_id="bg_x",
        payload={"task_id": "x"},
        actor="background",
    ).with_seq(1)
    item = ScheduledExecution(
        event_seq=1,
        event_id=evt.id,
        event_type="BackgroundTaskRequested",
        handler_name="on_bg_task_requested",
        instance_id="runtime:primary",
        _event=evt,
    )
    emit_execution_requested(kernel, item, "background")
    sch._pending.append(item)

    assert sch.request_cancel(item.id) is True
    assert all(i.id != item.id for i in sch._pending)
    rows = kernel.read_scheduled_executions(status="failed")
    assert any(r.id == item.id and r.error == "cancelled" for r in rows)


@pytest.mark.asyncio
async def test_cancel_background_task_api(kernel, monkeypatch):
    from app.api import background_tasks as api
    from app.core.runtime import read_ports
    from app.core.runtime.execution import is_background_task_cancelled
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
        PlanResume(kind="background", resume_from=1, task_id="c1"),
        db=kernel._db,
    )
    monkeypatch.setattr(
        "app.core.runtime.read_ports.timers.kernel",
        lambda: kernel,
    )
    monkeypatch.setattr(
        "app.core.runtime.runtime_container.runtime._scheduler",
        None,
    )
    monkeypatch.setattr(read_ports, "query_background_task", lambda tid: (
        (kernel.query_state("background_tasks", id=tid, limit=1) or [None])[0]
    ))

    result = await api.cancel_background_task("c1")
    assert result["status"] == "cancelled"
    # Flag stays until a handler acknowledges; durable row is authoritative.
    assert is_background_task_cancelled("c1")
    assert peek_plan_resume("apr_c1", db=kernel._db) is None
    configure_plan_resume_db(None)

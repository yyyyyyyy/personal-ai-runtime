"""Scheduler bounded pending queue / backpressure."""

from __future__ import annotations

import importlib

import pytest

from app.core.runtime.handler_registry import reset_handlers, subscribe
from app.core.runtime.kernel.event import Event
from app.core.runtime.kernel.kernel import Kernel
from app.core.runtime.scheduled_execution import ExecutionPolicy, ScheduledExecution
from app.store.database import Database


def _reregister_handlers() -> None:
    import app.core.agents.handlers.chat_completed_handlers as cch
    import app.core.agents.handlers.chat_handler as ch
    import app.core.agents.handlers.timer_trigger_handler as th
    import app.core.runtime.handlers.approve_handlers as ap
    import app.core.runtime.handlers.background_task_handlers as bg
    import app.core.runtime.handlers.execute_handlers as ex
    import app.core.runtime.handlers.inbox_poll_handlers as inbox

    for mod in (ch, cch, ap, ex, bg, inbox, th):
        importlib.reload(mod)


def _asch():
    """Fresh agent_scheduler module (survives conftest importlib.reload)."""
    import app.core.runtime.agent_scheduler as mod

    return mod


@pytest.fixture
def sch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.scheduler_max_pending",
        2,
    )
    reset_handlers()

    @subscribe("BpProbe")
    async def bp_handler(_ctx, _event):
        return None

    k = Kernel(db=Database(str(tmp_path / "bp.db")))
    s = _asch().Scheduler(k)
    s._pending.clear()
    yield s
    reset_handlers()
    _reregister_handlers()


def _event(seq: int = 1) -> Event:
    ev = Event(
        type="BpProbe",
        aggregate_type="probe",
        aggregate_id=f"p{seq}",
        payload={},
    )
    return ev.with_seq(seq)


def test_enqueue_within_limit(sch):
    items = sch.enqueue("runtime:primary", "runtime:primary", _event(1))
    assert len(items) == 1
    assert sch.pending_count() == 1
    assert not sch.is_queue_full()


def test_enqueue_rejects_when_full(sch):
    sch.enqueue("runtime:primary", "runtime:primary", _event(1))
    sch.enqueue("runtime:primary", "runtime:primary", _event(2))
    assert sch.is_queue_full()
    assert sch.pending_count() == 2

    with pytest.raises(_asch().SchedulerQueueFull):
        sch.enqueue("runtime:primary", "runtime:primary", _event(3))

    assert sch.pending_count() == 2
    failed = sch._kernel.read_scheduled_executions(status="failed")
    assert any(
        getattr(row, "error", None) == _asch().QUEUE_FULL_ERROR for row in failed
    )


@pytest.mark.asyncio
async def test_retry_fails_when_queue_full(sch, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.scheduler_max_pending",
        1,
    )
    item = ScheduledExecution(
        event_type="BpProbe",
        handler_name="bp_handler",
        instance_id="runtime:primary",
        event_seq=1,
        event_id="e1",
        error="boom",
        policy=ExecutionPolicy(max_retries=3, retry_delay_seconds=0),
        status="running",
        retry_count=0,
    )
    filler = ScheduledExecution(
        event_type="BpProbe",
        handler_name="bp_handler",
        instance_id="runtime:primary",
    )
    sch._pending = [filler]

    await sch._maybe_retry(item)
    assert item.status == "failed"
    assert item.error == _asch().QUEUE_FULL_ERROR
    assert filler in sch._pending
    assert item not in sch._pending


@pytest.mark.asyncio
async def test_queue_full_unblocks_submit_command(tmp_path, monkeypatch):
    """Backpressure resolves submit_command with queue_full instead of timeout."""
    import asyncio

    from app.core.runtime.kernel.event_dispatch import default_completion_type

    monkeypatch.setattr("app.config.settings.scheduler_max_pending", 1)
    reset_handlers()

    @subscribe("CmdRequested")
    async def cmd_handler(_ctx, _event):
        return None

    asch = _asch()
    k = Kernel(db=Database(str(tmp_path / "cmd_bp.db")))
    s = asch.Scheduler(k)
    s._pending.clear()

    filler = Event(
        type="CmdRequested",
        aggregate_type="cmd",
        aggregate_id="c0",
        payload={},
    ).with_seq(1)
    s.enqueue("runtime:primary", "runtime:primary", filler)

    corr = "cmd_bp_test"
    completion = default_completion_type("CmdRequested")
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    with k._commands_lock:
        k._pending_commands[(corr, completion)] = fut

    blocked = Event(
        type="CmdRequested",
        aggregate_type="cmd",
        aggregate_id="c1",
        payload={},
        correlation_id=corr,
    ).with_seq(2)

    with pytest.raises(asch.SchedulerQueueFull):
        s.enqueue("runtime:primary", "runtime:primary", blocked)

    await asyncio.wait_for(fut, timeout=1.0)
    assert fut.result().payload["error"] == asch.QUEUE_FULL_ERROR
    assert fut.result().payload["status"] == "error"

    reset_handlers()
    _reregister_handlers()

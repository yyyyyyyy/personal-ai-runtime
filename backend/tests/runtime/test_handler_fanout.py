"""Handler fan-out invariant: ChatCompleted registers both Lane A handlers."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

def _reregister_handlers() -> None:
    """Re-run @subscribe after autouse runtime.reset() cleared the registry."""
    import app.core.agents.handlers.chat_completed_handlers as cch
    import app.core.agents.handlers.chat_handler as ch
    import app.core.agents.handlers.timer_trigger_handler as th
    import app.core.runtime.handlers.approve_handlers as ap
    import app.core.runtime.handlers.background_task_handlers as bg
    import app.core.runtime.handlers.execute_handlers as ex
    import app.core.runtime.handlers.inbox_poll_handlers as inbox

    for mod in (ch, cch, ap, ex, bg, inbox, th):
        importlib.reload(mod)


def test_chat_completed_registers_both_handlers():
    """Both record_turn and extract_memories must remain registered (no overwrite)."""
    _reregister_handlers()
    from app.core.runtime.handler_registry import get_handlers

    names = {h.__name__ for h in get_handlers("ChatCompleted")}
    assert "on_chat_completed_record_turn" in names
    assert "on_chat_completed_extract_memories" in names
    assert len(names) >= 2


@pytest.mark.asyncio
async def test_scheduler_enqueues_one_execution_per_handler(tmp_path):
    from app.core.runtime.agent_scheduler import Scheduler
    from app.core.runtime.handler_registry import reset_handlers, subscribe
    from app.core.runtime.kernel.event import Event
    from app.core.runtime.kernel.kernel import Kernel
    from app.store.database import Database

    reset_handlers()
    seen: list[str] = []

    @subscribe("FanoutProbe")
    async def handler_one(_ctx, _event):
        seen.append("one")

    @subscribe("FanoutProbe")
    async def handler_two(_ctx, _event):
        seen.append("two")

    k = Kernel(db=Database(str(tmp_path / "fanout.db")))
    # Avoid real projection side-effects for Execution* in this unit probe:
    # Scheduler still calls emit; use a real kernel.
    sch = Scheduler(k)
    event = Event(
        type="FanoutProbe",
        aggregate_type="probe",
        aggregate_id="p1",
        payload={},
    )
    # Assign seq as emit would
    event = event.with_seq(1)

    items = sch.enqueue("runtime:primary", "runtime:primary", event)
    assert len(items) == 2
    assert {i.handler_name for i in items} == {"handler_one", "handler_two"}

    await sch.flush()
    assert set(seen) == {"one", "two"}

    reset_handlers()
    _reregister_handlers()


@pytest.mark.asyncio
async def test_chat_completed_record_turn_via_scheduler(tmp_path, monkeypatch):
    """ConversationRecorded must fire when ChatCompleted is scheduled (fan-out path)."""
    _reregister_handlers()
    import app.core.runtime.kernel_instance as ki
    from app.core.runtime.agent_scheduler import Scheduler
    from app.core.runtime.handler_registry import get_handlers
    from app.core.runtime.kernel.event import Event
    from app.core.runtime.kernel.kernel import Kernel
    from app.store.database import Database

    # Stub memory extract so this test does not call LLM.
    monkeypatch.setattr(
        "app.core.agents.handlers.chat_completed_handlers.memory_extractor",
        MagicMock(schedule=MagicMock()),
    )

    k = Kernel(db=Database(str(tmp_path / "chat_fanout.db")))
    # monkeypatch required: bare assignment leaks and splits emit vs read_ports.
    monkeypatch.setattr(ki, "kernel", k)

    assert len(get_handlers("ChatCompleted")) >= 2

    sch = Scheduler(k)
    event = Event(
        type="ChatCompleted",
        aggregate_type="chat",
        aggregate_id="chat_c1",
        payload={
            "conversation_id": "c1",
            "user_message": "hello fanout",
            "content": "hi there",
        },
    ).with_seq(1)

    items = sch.enqueue("runtime:primary", "runtime:primary", event)
    assert any(i.handler_name == "on_chat_completed_record_turn" for i in items)
    assert any(i.handler_name == "on_chat_completed_extract_memories" for i in items)

    await sch.flush()

    recorded = k.read_events(type="ConversationRecorded", aggregate_id="c1")
    assert len(recorded) == 1
    assert recorded[0].payload["user_message"] == "hello fanout"

def test_registered_types_includes_subscribed_key():
    from app.core.runtime.handler_registry import _registry, registered_types, subscribe

    key = "TestType_registry_probe"

    @subscribe(key)
    async def handle(_ctx, _evt):
        pass

    assert key in registered_types()
    _registry.pop(key, None)


def test_subscribe_fanout_appends_handlers():
    from app.core.runtime.handler_registry import _registry, get_handlers, subscribe

    key = "TestFanout_registry_probe"

    @subscribe(key)
    async def handler_a(_ctx, _evt):
        pass

    @subscribe(key)
    async def handler_b(_ctx, _evt):
        pass

    handlers = get_handlers(key)
    assert len(handlers) == 2
    assert {h.__name__ for h in handlers} == {"handler_a", "handler_b"}
    _registry.pop(key, None)

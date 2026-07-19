"""Tests for cron_registry — timer registration and event dispatch."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

EXPECTED_SCHEDULE_NAMES = {
    "deadline_alert",
    "memory_decay",
    "world_model_snapshot",
    "projection_snapshots",
    "inbox_poll",
    "inbox_digest",
    "morning_brief",
}


def test_schedules_has_all_timers():
    from app.core.runtime.cron_registry import SCHEDULES

    names = {s["name"] for s in SCHEDULES}
    assert EXPECTED_SCHEDULE_NAMES <= names


@pytest.mark.asyncio
async def test_on_task_completed_starts_dependents(tmp_path, monkeypatch):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "sched_task.db")))
    monkeypatch.setattr("app.core.runtime.cron_registry.kernel", k)
    monkeypatch.setattr("app.core.runtime.task_engine.kernel", k)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)

    k.emit_event("WorkItemCreated", "work_item", "t1", payload={"title": "Dep"})
    k.emit_event(
        "WorkItemCreated",
        "work_item",
        "t2",
        payload={"title": "Blocked", "dependencies_json": '["t1"]'},
    )
    k.emit_event("WorkItemStatusChanged", "work_item", "t1", payload={"status": "completed"}, actor="user")

    from app.core.runtime.cron_registry import _on_task_completed
    from app.core.runtime.kernel.event import Event

    evt = Event(
        type="WorkItemCompleted",
        aggregate_type="work_item",
        aggregate_id="t1",
        payload={"status": "completed"},
    )
    _on_task_completed(evt)

    task2 = k.query_state("work_items", id="t2")[0]
    assert task2["status"] == "running"


def test_shutdown_scheduler_unsubscribes_triggers(tmp_path, monkeypatch):
    """shutdown_scheduler clears WorkItem* subscriptions from init_scheduler."""
    from app.core.runtime import cron_registry as cr
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "cron_unsub.db")))
    monkeypatch.setattr("app.core.runtime.cron_registry.kernel", k)
    monkeypatch.setattr(
        "app.core.runtime.cron_registry.read_ports.query_timer",
        lambda name: {"id": name},
    )
    cr.shutdown_scheduler()
    before = len(k._subscribers)
    cr.init_scheduler()
    assert len(k._subscribers) == before + 2
    cr.shutdown_scheduler()
    assert len(k._subscribers) == before

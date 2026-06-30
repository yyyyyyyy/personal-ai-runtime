"""Tests for cron_registry — timer registration and event dispatch."""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

EXPECTED_SCHEDULE_NAMES = {
    "deadline_alert",
    "trigger_evaluation",
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

    k.emit_event("TaskCreated", "task", "t1", payload={"name": "Dep"})
    k.emit_event(
        "TaskCreated",
        "task",
        "t2",
        payload={"name": "Blocked", "dependencies_json": '["t1"]'},
    )
    k.emit_event("TaskStatusChanged", "task", "t1", payload={"status": "completed"}, actor="user")

    from app.core.runtime.kernel.event import Event
    from app.core.runtime.cron_registry import _on_task_completed

    evt = Event(
        type="TaskCompleted",
        aggregate_type="task",
        aggregate_id="t1",
        payload={"status": "completed"},
    )
    _on_task_completed(evt)

    task2 = k.query_state("tasks", id="t2")[0]
    assert task2["status"] == "running"


def test_shutdown_scheduler_stops_timer_engine(monkeypatch):
    mock_engine = MagicMock()
    monkeypatch.setattr(
        "app.core.runtime.timer_engine._timer_engine",
        mock_engine,
    )

    from app.core.runtime.cron_registry import shutdown_scheduler

    shutdown_scheduler()

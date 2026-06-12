"""Tests for Scheduler v2 — job registration and event dispatch."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

EXPECTED_JOB_IDS = {
    "morning_brief",
    "daily_review",
    "belief_reflection",
    "weekly_review",
    "monthly_review",
    "deadline_alert",
    "trigger_evaluation",
    "memory_decay",
    "world_model_snapshot",
    "projection_snapshots",
    "inbox_poll",
    "inbox_digest",
}


def test_init_registers_expected_jobs(monkeypatch):
    mock_sched = MagicMock()
    mock_sched.running = False
    monkeypatch.setattr("app.core.runtime.scheduler_v2._scheduler", mock_sched)
    monkeypatch.setattr("app.core.runtime.scheduler_v2._sync_v2_schedules_to_db", lambda: None)
    monkeypatch.setattr(
        "app.core.runtime.scheduler_v2.event_bus.subscribe",
        MagicMock(),
    )

    from app.core.runtime.scheduler_v2 import init_scheduler_v2

    init_scheduler_v2()

    ids = {call.kwargs["id"] for call in mock_sched.add_job.call_args_list}
    assert EXPECTED_JOB_IDS <= ids
    mock_sched.start.assert_called_once()


@pytest.mark.asyncio
async def test_on_schedule_triggered_dispatches_inbox_poll(monkeypatch):
    called: dict[str, bool] = {}

    def fake_inbox_poll():
        called["inbox_poll"] = True

    monkeypatch.setattr(
        "app.core.runtime.scheduler_v2._run_inbox_poll",
        fake_inbox_poll,
    )

    from app.core.runtime.scheduler_v2 import _on_schedule_triggered

    await _on_schedule_triggered("schedule_triggered", {"task_type": "inbox_poll"})
    assert called.get("inbox_poll") is True


@pytest.mark.asyncio
async def test_on_task_completed_starts_dependents(tmp_path, monkeypatch):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    k = Kernel(db=Database(db_path=str(tmp_path / "sched_task.db")))
    monkeypatch.setattr("app.core.runtime.scheduler_v2.kernel", k)
    monkeypatch.setattr("app.core.runtime.task_engine.kernel", k)

    k.emit_event("TaskCreated", "task", "t1", payload={"name": "Dep"})
    k.emit_event(
        "TaskCreated",
        "task",
        "t2",
        payload={"name": "Blocked", "dependencies_json": '["t1"]'},
    )
    k.change_task_status("t1", "completed", actor="user")

    from app.core.runtime.scheduler_v2 import _on_task_completed

    await _on_task_completed("task_completed", {"task_id": "t1"})

    task2 = k.query_state("tasks", id="t2")[0]
    assert task2["status"] == "running"


@patch("app.product.inbox.poll_inbox", new_callable=AsyncMock)
def test_run_inbox_poll_invokes_product_layer(mock_poll):
    mock_poll.return_value = {"status": "ok"}

    from app.core.runtime.scheduler_v2 import _run_inbox_poll

    _run_inbox_poll()
    mock_poll.assert_called_once()


@patch("app.core.runtime.notification_bridge.push_notification")
@patch("app.product.morning_brief.generate_morning_brief")
def test_run_morning_brief_notifies_when_content(mock_brief, mock_push):
    mock_brief.return_value = {"title": "早安", "content": "今日简报"}

    from app.core.runtime.scheduler_v2 import _run_morning_brief

    _run_morning_brief()
    mock_push.assert_called_once_with("brief", "早安", "今日简报")


def test_trigger_event_schedule_publishes(monkeypatch):
    published: list[tuple] = []

    def capture(event_type, payload):
        published.append((event_type, payload))

    monkeypatch.setattr(
        "app.core.runtime.scheduler_v2.event_bus.publish",
        capture,
    )

    from app.core.runtime.event_bus import EventType
    from app.core.runtime.scheduler_v2 import trigger_event_schedule

    trigger_event_schedule("deadline_alert", {"foo": "bar"})
    assert published == [(EventType.SCHEDULE_TRIGGERED, {"task_type": "deadline_alert", "payload": {"foo": "bar"}})]


def test_shutdown_scheduler_v2_stops_running_scheduler(monkeypatch):
    mock_sched = MagicMock()
    mock_sched.running = True
    monkeypatch.setattr("app.core.runtime.scheduler_v2._scheduler", mock_sched)

    from app.core.runtime.scheduler_v2 import shutdown_scheduler_v2

    shutdown_scheduler_v2()
    mock_sched.shutdown.assert_called_once_with(wait=False)

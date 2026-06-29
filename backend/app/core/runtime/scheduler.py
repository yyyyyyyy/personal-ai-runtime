"""Cron scheduler — timer-driven scheduling via Runtime Timer Engine.

Distinct from agent_scheduler.py (WorkItem execution): this module
registers cron schedules and starts the TimerEngine. It does not execute
handlers itself — TimerFired events flow into the WorkItem engine.

Timers are Runtime aggregates: TimerCreated events register future fire times
in the timer_events projection. The TimerEngine scans every second and emits
TimerFired when due. The timer_trigger_handler subscribes to TimerFired and
executes product functions within Execution context.

Dependency triggers (TaskCompleted → dependent task start) are kernel-event-driven.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)

SCHEDULES: list[dict] = [
    {"name": "belief_reflection", "cron_expr": "hour=21,minute=30", "schedule_type": "cron", "handler_name": "belief_reflection"},
    {"name": "morning_brief", "cron_expr": "hour=8,minute=0", "schedule_type": "cron", "handler_name": "morning_brief"},
    {"name": "deadline_alert", "cron_expr": "hour=9,minute=0", "schedule_type": "cron", "handler_name": "deadline_alert"},
    {"name": "trigger_evaluation", "cron_expr": "minute=*/30", "schedule_type": "cron", "handler_name": "trigger_evaluation"},
    {"name": "memory_decay", "cron_expr": "hour=3,minute=0", "schedule_type": "cron", "handler_name": "memory_decay"},
    {"name": "world_model_snapshot", "cron_expr": "day_of_week=sun,hour=6,minute=0", "schedule_type": "cron", "handler_name": "world_model_snapshot"},
    {"name": "projection_snapshots", "cron_expr": "hour=4,minute=0", "schedule_type": "cron", "handler_name": "projection_snapshots"},
    {"name": "inbox_poll", "cron_expr": "minute=*/15", "schedule_type": "cron", "handler_name": "inbox_poll"},
    {"name": "inbox_digest", "cron_expr": "hour=8,minute=30", "schedule_type": "cron", "handler_name": "inbox_digest"},
]


def init_scheduler():
    """Register timer schedules and start the TimerEngine."""
    kernel.subscribe_events(_on_task_completed, type="TaskCompleted")
    kernel.subscribe_events(_on_task_completed, type="TaskStatusChanged")
    _init_timers()


def _init_timers():
    """Register TimerCreated events and start the TimerEngine."""
    from app.core.runtime.timer_engine import get_timer_engine

    engine = get_timer_engine(kernel)
    engine.ensure_schedules(SCHEDULES)

    import asyncio as _asyncio

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(engine.start())
    else:
        logger.info("TimerEngine start deferred (no running loop)")


def shutdown_scheduler():
    """Shutdown the TimerEngine gracefully."""
    from app.core.runtime.timer_engine import get_current_timer_engine

    engine = get_current_timer_engine()
    if engine is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(engine.stop())
        except RuntimeError:
            pass


def _on_task_completed(event):
    """When a task completes, start dependents whose dependencies are met."""
    task_id = event.aggregate_id
    if event.type == "TaskStatusChanged":
        status = (event.payload or {}).get("status")
        if status not in ("completed", "failed"):
            return
    rows = kernel.query_state(
        "tasks",
        status="pending",
        depends_on_task=task_id,
    )

    from app.core.runtime.task_engine import task_engine

    for task in rows:
        if task_engine.are_dependencies_met(task["id"]):
            task_engine.update_task_status(task["id"], "running")


def _deadline_target_dates() -> set:
    """Return the set of dates (UTC) that trigger deadline alerts."""
    today_utc = datetime.now(UTC).date()
    return {today_utc + timedelta(days=offset) for offset in (1, 3)}


def trigger_event_schedule(task_type: str, payload: dict | None = None):
    """Programmatically trigger a scheduled task via event (for testing)."""
    event_bus.publish(EventType.SCHEDULE_TRIGGERED, {
        "task_type": task_type,
        "payload": payload or {},
    })

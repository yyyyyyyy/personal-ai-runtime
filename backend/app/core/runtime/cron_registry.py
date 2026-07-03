"""Cron scheduler — timer-driven scheduling via Runtime Timer Engine.

v0.3.0: Timer scanning is now driven by RuntimeLoop. This module retains
cron registration (ensure_schedules) and dependency triggers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)

SCHEDULES: list[dict] = [
    {"name": "morning_brief", "cron_expr": "hour=8,minute=0", "schedule_type": "cron", "handler_name": "morning_brief"},
    {"name": "deadline_alert", "cron_expr": "hour=9,minute=0", "schedule_type": "cron", "handler_name": "deadline_alert"},
    {"name": "memory_decay", "cron_expr": "hour=3,minute=0", "schedule_type": "cron", "handler_name": "memory_decay"},
    {"name": "world_model_snapshot", "cron_expr": "day_of_week=sun,hour=6,minute=0", "schedule_type": "cron", "handler_name": "world_model_snapshot"},
    {"name": "projection_snapshots", "cron_expr": "hour=4,minute=0", "schedule_type": "cron", "handler_name": "projection_snapshots"},
    {"name": "inbox_poll", "cron_expr": "minute=*/15", "schedule_type": "cron", "handler_name": "inbox_poll"},
    {"name": "inbox_digest", "cron_expr": "hour=8,minute=30", "schedule_type": "cron", "handler_name": "inbox_digest"},
]


def init_scheduler():
    """Register timer schedules and dependency triggers."""
    kernel.subscribe_events(_on_task_completed, type="TaskCompleted")
    kernel.subscribe_events(_on_task_completed, type="TaskStatusChanged")
    _init_timers()


def _init_timers():
    """Register TimerCreated events for all scheduled cron jobs."""
    from app.core.runtime.timer_engine import ensure_schedules

    ensure_schedules(SCHEDULES)


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


def shutdown_scheduler():
    """Shutdown stub — timer scanning is now handled by RuntimeLoop."""
    pass

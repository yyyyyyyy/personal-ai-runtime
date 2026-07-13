"""Cron scheduler — timer-driven scheduling via Runtime Timer Engine.

v0.4.0: ensure_schedules inlined from deleted timer_engine.py.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_loop import RuntimeLoop

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
    kernel.subscribe_events(_on_task_completed, type="WorkItemCompleted")
    kernel.subscribe_events(_on_task_completed, type="WorkItemStatusChanged")
    _init_timers()


def _init_timers():
    """Register TimerCreated events for all scheduled cron jobs."""
    for sched in SCHEDULES:
        name = sched["name"]
        existing = read_ports.query_timer(name)
        if existing:
            continue
        cron_expr = sched.get("cron_expr", "")
        next_fire = RuntimeLoop._next_cron_fire(cron_expr)
        kernel.emit_event(
            "TimerCreated", "timer", name,
            payload={
                "handler_name": sched.get("handler_name", ""),
                "schedule_type": sched.get("schedule_type", "cron"),
                "cron_expr": cron_expr,
                "fire_at": next_fire,
            },
            actor="system",
        )


def _on_task_completed(event):
    """When a work item completes, start dependents whose dependencies are met."""
    if event.type == "WorkItemStatusChanged":
        status = (event.payload or {}).get("status")
        if status not in ("completed", "failed"):
            return

    from app.core.runtime.task_engine import are_dependencies_met

    rows = read_ports.query_pending_work_items(limit=100)
    for item in rows:
        if are_dependencies_met(item["id"]):
            kernel.emit_event(
                "WorkItemStatusChanged", "work_item", item["id"],
                payload={"status": "running"}, actor="system",
            )


def _deadline_target_dates() -> set:
    """Return the set of dates (local) that trigger deadline alerts."""
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        tz = UTC
    today = datetime.now(tz).date()
    return {today + timedelta(days=offset) for offset in (1, 3)}


def shutdown_scheduler():
    """Shutdown stub — timer scanning is now handled by RuntimeLoop."""
    pass


def run_memory_decay(threshold: float = 0.3, decay_to: float = 0.1) -> int:
    """Emit MemoryDecayed for stale low-confidence memories (daily cron)."""
    count = 0
    candidates = read_ports.query_memories(
        confidence_gt=decay_to,
        confidence_lt=0.8,
        decay_eligible=True,
        limit=50,
    )
    for mem in candidates:
        if mem["confidence"] <= threshold:
            new_conf = max(decay_to, mem["confidence"] - 0.1)
            kernel.emit_event(
                type="MemoryDecayed",
                aggregate_type="memory",
                aggregate_id=mem["id"],
                payload={"confidence": new_conf},
                actor="scheduler",
            )
            count += 1
    return count

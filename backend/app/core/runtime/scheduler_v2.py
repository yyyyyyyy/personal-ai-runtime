"""Scheduler v2 — supports Cron, Event, and Dependency triggers.

Extends the old scheduler.py with event-driven and dependency-driven scheduling.
The old scheduler.py continues to run in parallel during migration.
"""

import uuid
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.runtime.event_bus import EventType, event_bus
from app.store.database import db

_scheduler = BackgroundScheduler()


async def _on_task_completed(event_type: str, payload: dict):
    """Dependency trigger: when a task completes, check if dependents can start."""
    task_id = payload.get("task_id", "")
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE dependencies_json LIKE ? AND status = 'pending'",
            (f"%{task_id}%",),
        ).fetchall()

    from app.core.runtime.task_engine import task_engine
    for row in rows:
        task = dict(row)
        if task_engine.are_dependencies_met(task["id"]):
            task_engine.update_task_status(task["id"], "running")


async def _on_schedule_triggered(event_type: str, payload: dict):
    """Event trigger: handle schedule-triggered events and dispatch to handlers."""
    task_type = payload.get("task_type", "")
    if task_type == "morning_brief":
        _run_morning_brief()
    elif task_type == "daily_review":
        _run_daily_review()
    elif task_type == "weekly_review":
        _run_weekly_review()
    elif task_type == "monthly_review":
        _run_monthly_review()
    elif task_type == "deadline_alert":
        _run_deadline_alert()


def init_scheduler_v2():
    """Initialize Scheduler v2 with all trigger types and start it."""
    # Subscribe to dependency triggers
    event_bus.subscribe(EventType.TASK_COMPLETED, _on_task_completed)

    # Subscribe to event-based schedule triggers
    event_bus.subscribe(EventType.SCHEDULE_TRIGGERED, _on_schedule_triggered)

    # Register cron-based tasks (same as old scheduler + new ones)
    _scheduler.add_job(
        _run_morning_brief,
        CronTrigger(hour=8, minute=0),
        id="morning_brief",
        name="晨间简报",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_daily_review,
        CronTrigger(hour=21, minute=0),
        id="daily_review",
        name="每日复盘",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_weekly_review,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_review",
        name="每周复盘",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_monthly_review,
        CronTrigger(day=1, hour=20, minute=0),
        id="monthly_review",
        name="每月复盘",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_deadline_alert,
        CronTrigger(hour=9, minute=0),
        id="deadline_alert",
        name="Deadline预警",
        replace_existing=True,
    )

    # Sync to database
    _sync_v2_schedules_to_db()

    if not _scheduler.running:
        _scheduler.start()


def shutdown_scheduler_v2():
    """Shutdown Scheduler v2 gracefully."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def trigger_event_schedule(task_type: str, payload: dict | None = None):
    """Programmatically trigger a scheduled task via event (for testing or manual triggers)."""
    event_bus.publish(EventType.SCHEDULE_TRIGGERED, {
        "task_type": task_type,
        "payload": payload or {},
    })


def _sync_v2_schedules_to_db():
    """Sync scheduler jobs to the schedules table with trigger_type."""
    jobs = _scheduler.get_jobs()
    with db.get_db() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM schedules WHERE name = ?", (job.name,)
            ).fetchone()
            if not existing:
                schedule_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO schedules (id, name, cron_expr, task_type, trigger_type, enabled, created_at)
                       VALUES (?, ?, ?, ?, 'cron', 1, ?)""",
                    (schedule_id, job.name, str(job.trigger), job.id, datetime.utcnow().isoformat()),
                )


def _run_morning_brief():
    try:
        from app.product.morning_brief import generate_morning_brief
        generate_morning_brief()
        _update_v2_last_run("morning_brief")
    except Exception as e:
        print(f"Morning brief error: {e}")


def _run_daily_review():
    try:
        from app.product.daily_review import generate_daily_review
        generate_daily_review()
        _update_v2_last_run("daily_review")
    except Exception as e:
        print(f"Daily review error: {e}")


def _run_weekly_review():
    try:
        from app.product.weekly_review import generate_weekly_review
        generate_weekly_review()
        _update_v2_last_run("weekly_review")
    except Exception as e:
        print(f"Weekly review error: {e}")


def _run_monthly_review():
    try:
        from app.product.monthly_review import generate_monthly_review
        generate_monthly_review()
        _update_v2_last_run("monthly_review")
    except Exception as e:
        print(f"Monthly review error: {e}")


def _run_deadline_alert():
    try:
        with db.get_db() as conn:
            deadlines = conn.execute(
                """SELECT * FROM goals WHERE status = 'active'
                   AND deadline IS NOT NULL
                   AND date(deadline) IN (date('now', '+1 days'), date('now', '+3 days'))
                   ORDER BY deadline ASC"""
            ).fetchall()

        for goal in deadlines:
            goal = dict(goal)
            delta = datetime.fromisoformat(goal["deadline"]) - datetime.utcnow()
            days_left = delta.days

            notification_id = str(uuid.uuid4())
            title = "Deadline 预警"
            content = f"目标「{goal['title']}」还有 {days_left} 天截止"

            with db.get_db() as conn:
                conn.execute(
                    "INSERT INTO notifications (id, type, title, content, created_at) "
                    "VALUES (?, 'alert', ?, ?, ?)",
                    (notification_id, title, content, datetime.utcnow().isoformat()),
                )

        _update_v2_last_run("deadline_alert")
    except Exception as e:
        print(f"Deadline alert error: {e}")


def _update_v2_last_run(task_name: str):
    with db.get_db() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at = ? WHERE name = ?",
            (datetime.utcnow().isoformat(), task_name),
        )

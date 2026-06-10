"""Task Scheduler — manages timed tasks using APScheduler.

Handles:
- Morning brief (daily 8:00)
- Daily review (daily 21:00)
- Weekly review (Sunday 20:00)
- Monthly review (1st of month 20:00)
- Deadline alerts (daily 9:00)
"""

import uuid
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.store.database import db

_scheduler = BackgroundScheduler()


def init_scheduler():
    """Initialize the scheduler with default tasks and start it."""

    # Morning brief: every day at 8:00
    _scheduler.add_job(
        _run_morning_brief,
        CronTrigger(hour=8, minute=0),
        id="morning_brief",
        name="晨间简报",
        replace_existing=True,
    )

    # Daily review: every day at 21:00
    _scheduler.add_job(
        _run_daily_review,
        CronTrigger(hour=21, minute=0),
        id="daily_review",
        name="每日复盘",
        replace_existing=True,
    )

    # Weekly review: Sunday at 20:00
    _scheduler.add_job(
        _run_weekly_review,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_review",
        name="每周复盘",
        replace_existing=True,
    )

    # Monthly review: 1st of the month at 20:00
    _scheduler.add_job(
        _run_monthly_review,
        CronTrigger(day=1, hour=20, minute=0),
        id="monthly_review",
        name="每月复盘",
        replace_existing=True,
    )

    # Deadline alerts: every day at 9:00
    _scheduler.add_job(
        _run_deadline_alert,
        CronTrigger(hour=9, minute=0),
        id="deadline_alert",
        name="Deadline预警",
        replace_existing=True,
    )

    # Sync scheduled tasks to database
    _sync_schedules_to_db()

    if not _scheduler.running:
        _scheduler.start()


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def _sync_schedules_to_db():
    """Sync scheduler jobs to the schedules table."""
    jobs = _scheduler.get_jobs()
    with db.get_db() as conn:
        for job in jobs:
            existing = conn.execute(
                "SELECT id FROM schedules WHERE name = ?", (job.name,)
            ).fetchone()
            if not existing:
                schedule_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO schedules (id, name, cron_expr, task_type, enabled, created_at) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (schedule_id, job.name, str(job.trigger), job.id, datetime.utcnow().isoformat()),
                )


def _run_morning_brief():
    """Execute morning brief generation."""
    try:
        from app.product.morning_brief import generate_morning_brief
        result = generate_morning_brief()
        _update_last_run("morning_brief")
        return result
    except Exception as e:
        print(f"Morning brief error: {e}")


def _run_daily_review():
    """Execute daily review generation."""
    try:
        from app.product.daily_review import generate_daily_review
        result = generate_daily_review()
        _update_last_run("daily_review")
        return result
    except Exception as e:
        print(f"Daily review error: {e}")


def _run_weekly_review():
    """Execute weekly review generation."""
    try:
        from app.product.weekly_review import generate_weekly_review
        result = generate_weekly_review()
        _update_last_run("weekly_review")
        return result
    except Exception as e:
        print(f"Weekly review error: {e}")


def _run_monthly_review():
    """Execute monthly review generation."""
    try:
        from app.product.monthly_review import generate_monthly_review
        result = generate_monthly_review()
        _update_last_run("monthly_review")
        return result
    except Exception as e:
        print(f"Monthly review error: {e}")


def _run_deadline_alert():
    """Check for imminent deadlines and create alerts."""
    try:
        today_utc = datetime.utcnow().date()
        target_dates = {today_utc + timedelta(days=offset) for offset in (1, 3)}

        with db.get_db() as conn:
            deadlines = conn.execute(
                """SELECT * FROM goals WHERE status = 'active'
                   AND deadline IS NOT NULL
                   AND date(deadline) IN (date('now', '+1 days'), date('now', '+3 days'))
                   ORDER BY deadline ASC"""
            ).fetchall()

        # Filter in Python with UTC dates for consistency when date() parsing differs
        filtered = []
        for goal in deadlines:
            goal = dict(goal)
            try:
                deadline_date = datetime.fromisoformat(goal["deadline"]).date()
            except ValueError:
                continue
            if deadline_date in target_dates:
                filtered.append(goal)
        deadlines = filtered

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

        _update_last_run("deadline_alert")
    except Exception as e:
        print(f"Deadline alert error: {e}")


def _update_last_run(task_name: str):
    """Update the last_run_at timestamp for a schedule."""
    with db.get_db() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at = ? WHERE name = ?",
            (datetime.utcnow().isoformat(), task_name),
        )

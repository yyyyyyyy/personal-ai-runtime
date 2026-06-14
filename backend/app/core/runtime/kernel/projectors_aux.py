# --- Notification projection -------------------------------------------------

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["notification"] = ["notifications"]


@projector("NotificationCreated")
def _on_notification_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO notifications
           (id, type, title, content, read, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (
            event.aggregate_id,
            p.get("type", ""),
            p.get("title", ""),
            p.get("content", ""),
            p.get("created_at", event.ts),
        ),
    )


@projector("NotificationUpdated")
def _on_notification_updated(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE notifications SET content = ? WHERE id = ?",
        (p.get("content", ""), event.aggregate_id),
    )


@projector("NotificationRead")
def _on_notification_read(event: Event, conn) -> None:
    conn.execute(
        "UPDATE notifications SET read = 1 WHERE id = ?",
        (event.aggregate_id,),
    )


@projector("NotificationReadAll")
def _on_notification_read_all(event: Event, conn) -> None:
    conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")


# --- Schedule projection -----------------------------------------------------

_OWNED_TABLES["schedule"] = ["schedules"]


@projector("ScheduleCreated")
def _on_schedule_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO schedules
           (id, name, cron_expr, task_type, trigger_type, trigger_config, config,
            enabled, last_run_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("name", ""),
            p.get("cron_expr", ""),
            p.get("task_type", ""),
            p.get("trigger_type", "cron"),
            p.get("trigger_config"),
            p.get("config"),
            1 if p.get("enabled", True) else 0,
            p.get("last_run_at"),
            p.get("created_at", event.ts),
        ),
    )


@projector("ScheduleLastRunUpdated")
def _on_schedule_last_run_updated(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE schedules SET last_run_at = ? WHERE id = ?",
        (p.get("last_run_at", event.ts), event.aggregate_id),
    )

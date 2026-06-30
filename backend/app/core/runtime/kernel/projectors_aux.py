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

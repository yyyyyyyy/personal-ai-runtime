"""Notifications API — list, mark as read, and get notifications."""

from fastapi import APIRouter

from app.store.database import db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/")
async def list_notifications(unread_only: bool = False, limit: int = 50):
    """List notifications, optionally filtered to unread only."""
    with db.get_db() as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/unread-count")
async def unread_count():
    """Get count of unread notifications."""
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM notifications WHERE read = 0"
        ).fetchone()
    return {"count": row["count"] if row else 0}


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str):
    """Mark a notification as read."""
    with db.get_db() as conn:
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,)
        )
    return {"status": "ok"}


@router.put("/read-all")
async def mark_all_as_read():
    """Mark all notifications as read."""
    with db.get_db() as conn:
        conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return {"status": "ok"}

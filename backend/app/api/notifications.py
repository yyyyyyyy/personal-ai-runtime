"""Notifications API — list, mark as read, and get notifications."""

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime.kernel.constants import (
    AGGREGATE_NOTIFICATION,
    EVENT_NOTIFICATION_READ,
    EVENT_NOTIFICATION_READ_ALL,
)
from app.core.runtime.kernel_instance import kernel

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/")
async def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=500)):
    """List notifications, optionally filtered to unread only."""
    rows = kernel.query_state(
        "notifications",
        unread_only=unread_only,
        limit=limit,
    )
    return [dict(r) for r in rows]


@router.get("/unread-count")
async def unread_count():
    """Get count of unread notifications."""
    rows = kernel.query_state("notifications", unread_only=True, limit=10_000)
    return {"count": len(rows)}


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str):
    """Mark a notification as read."""
    existing = kernel.query_state("notifications", id=notification_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Notification not found")
    kernel.emit_event(
        EVENT_NOTIFICATION_READ,
        AGGREGATE_NOTIFICATION,
        notification_id,
        payload={},
        actor="user",
    )
    return {"status": "ok"}


@router.put("/read-all")
async def mark_all_as_read():
    """Mark all notifications as read."""
    kernel.emit_event(
        EVENT_NOTIFICATION_READ_ALL,
        AGGREGATE_NOTIFICATION,
        "all",
        payload={},
        actor="user",
    )
    return {"status": "ok"}

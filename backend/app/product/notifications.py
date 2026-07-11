"""Notification generation utilities — writes go through Kernel Event Log."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.runtime import read_ports
from app.core.runtime.kernel.constants import (
    AGGREGATE_NOTIFICATION,
    EVENT_NOTIFICATION_CREATED,
    EVENT_NOTIFICATION_UPDATED,
)
from app.core.runtime.kernel_instance import kernel as default_kernel

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel


def _kernel(k: "Kernel | None" = None) -> "Kernel":
    return k or default_kernel


def find_notification(
    notif_type: str,
    title: str,
    *,
    kernel: "Kernel | None" = None,
) -> dict | None:
    """Return an existing notification with the same type and title, if any."""
    if kernel is None:
        rows = read_ports.query_notifications(
            type=notif_type, title=title, limit=1,
        )
    else:
        rows = kernel.query_state(
            "notifications", type=notif_type, title=title, limit=1,
        )
    return rows[0] if rows else None


def create_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    related_id: str | None = None,
    related_type: str | None = None,
    kernel: "Kernel | None" = None,
) -> dict:
    """Create a notification and return it (idempotent by type + title).

    ``related_id`` is stored in the notifications.related_id column via the
    projector — not embedded in content.
    """
    k = _kernel(kernel)
    existing = find_notification(notif_type, title, kernel=k)
    if existing:
        if related_id and not existing.get("related_id"):
            k.emit_event(
                EVENT_NOTIFICATION_UPDATED,
                AGGREGATE_NOTIFICATION,
                existing["id"],
                payload={
                    "content": existing.get("content", content),
                    "related_id": related_id,
                    "related_type": related_type,
                },
                actor="system",
            )
            existing = {
                **existing,
                "related_id": related_id,
                "related_type": related_type,
            }
        return existing

    nid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    k.emit_event(
        EVENT_NOTIFICATION_CREATED,
        AGGREGATE_NOTIFICATION,
        nid,
        payload={
            "type": notif_type,
            "title": title,
            "content": content,
            "related_id": related_id,
            "related_type": related_type,
            "notification_type": notif_type,
            "created_at": now,
        },
        actor="system",
    )
    return {
        "id": nid,
        "type": notif_type,
        "title": title,
        "content": content,
        "related_id": related_id,
        "related_type": related_type,
        "created_at": now,
    }

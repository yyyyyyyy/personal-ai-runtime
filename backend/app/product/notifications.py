"""Notification generation utilities — writes go through Kernel Event Log."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

from app.core.runtime import read_ports
from app.core.runtime.kernel.constants import (
    AGGREGATE_NOTIFICATION,
    EVENT_NOTIFICATION_CREATED,
    EVENT_NOTIFICATION_UPDATED,
)
from app.core.runtime.kernel_instance import kernel as default_kernel

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel


class NotificationPayload(TypedDict, total=False):
    id: str
    type: str
    title: str
    content: str
    read: int
    related_id: str | None
    related_type: str | None
    notification_type: str
    dedup_key: str | None
    created_at: str


def _kernel(k: "Kernel | None" = None) -> "Kernel":
    return k or default_kernel


def find_notification(
    notif_type: str,
    title: str | None = None,
    *,
    dedup_key: str | None = None,
    kernel: "Kernel | None" = None,
) -> NotificationPayload | None:
    """Return an existing notification by dedup_key or type+title, if any."""
    kwargs = {"type": notif_type, "limit": 1}
    if dedup_key is not None:
        kwargs["dedup_key"] = dedup_key
    elif title is not None:
        kwargs["title"] = title

    if kernel is None:
        rows = read_ports.query_notifications(**kwargs)
    else:
        rows = kernel.query_state("notifications", **kwargs)
    return rows[0] if rows else None


def create_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    related_id: str | None = None,
    related_type: str | None = None,
    dedup_key: str | None = None,
    actor: str = "system",
    kernel: "Kernel | None" = None,
) -> NotificationPayload:
    """Create a notification and return it (idempotent by dedup_key or type + title).

    ``related_id`` is stored in the notifications.related_id column via the
    projector — not embedded in content.
    """
    k = _kernel(kernel)
    existing = find_notification(
        notif_type, title, dedup_key=dedup_key, kernel=k
    )
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
                actor=actor,
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
            "dedup_key": dedup_key,
            "created_at": now,
        },
        actor=actor,
    )
    return {
        "id": nid,
        "type": notif_type,
        "title": title,
        "content": content,
        "related_id": related_id,
        "related_type": related_type,
        "notification_type": notif_type,
        "dedup_key": dedup_key,
        "created_at": now,
    }

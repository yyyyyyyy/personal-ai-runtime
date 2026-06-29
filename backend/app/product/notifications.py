"""Notification generation utilities — writes go through Kernel Event Log."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
    rows = _kernel(kernel).query_state(
        "notifications", type=notif_type, title=title, limit=1
    )
    return rows[0] if rows else None


def _embed_related_id(content: str, related_id: str | None) -> str:
    if related_id:
        return f"@related:{related_id}\n{content}"
    return content


def parse_related_id(content: str) -> tuple[str | None, str]:
    """Extract optional related entity id prefix from notification content."""
    if content.startswith("@related:"):
        first_line, _, rest = content.partition("\n")
        return first_line.removeprefix("@related:"), rest
    return None, content


def create_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    related_id: str | None = None,
    kernel: "Kernel | None" = None,
) -> dict:
    """Create a notification and return it (idempotent by type + title)."""
    k = _kernel(kernel)
    existing = find_notification(notif_type, title, kernel=k)
    if existing:
        if related_id and not existing["content"].startswith("@related:"):
            _, body = parse_related_id(existing["content"])
            updated = _embed_related_id(body, related_id)
            k.emit_event(
                EVENT_NOTIFICATION_UPDATED,
                AGGREGATE_NOTIFICATION,
                existing["id"],
                payload={"content": updated},
                actor="system",
            )
            existing = {**existing, "content": updated}
        return existing

    stored_content = _embed_related_id(content, related_id)
    nid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    k.emit_event(
        EVENT_NOTIFICATION_CREATED,
        AGGREGATE_NOTIFICATION,
        nid,
        payload={
            "type": notif_type,
            "title": title,
            "content": stored_content,
            "created_at": now,
        },
        actor="system",
    )
    return {
        "id": nid,
        "type": notif_type,
        "title": title,
        "content": stored_content,
        "created_at": now,
    }

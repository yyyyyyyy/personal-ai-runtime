"""Notification projection read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def query_notification(notification_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("notifications", id=notification_id, limit=1)
    return rows[0] if rows else None


def query_notifications(
    *,
    unread_only: bool = False,
    limit: int = 50,
    type: str | None = None,
    title: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if unread_only:
        filters["unread_only"] = True
    if type:
        filters["type"] = type
    if title is not None:
        filters["title"] = title
    if order:
        filters["order"] = order
    return kernel().query_state("notifications", **filters)


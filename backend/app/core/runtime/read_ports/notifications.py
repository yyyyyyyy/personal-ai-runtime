"""Notification ports — projection reads plus push / SSE bridge ABI."""

from __future__ import annotations

import logging
from typing import Any

from app.core.runtime.read_ports._common import kernel

logger = logging.getLogger(__name__)


def query_notification(notification_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("notifications", id=notification_id, limit=1)
    return rows[0] if rows else None


def query_notifications(
    *,
    unread_only: bool = False,
    limit: int = 50,
    type: str | None = None,
    title: str | None = None,
    dedup_key: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if unread_only:
        filters["unread_only"] = True
    if type:
        filters["type"] = type
    if title is not None:
        filters["title"] = title
    if dedup_key is not None:
        filters["dedup_key"] = dedup_key
    if order:
        filters["order"] = order
    return kernel().query_state("notifications", **filters)


def query_unread_notification_count() -> int:
    """Exact unread notification COUNT (not capped by list LIMIT)."""
    try:
        return kernel().count_state("notifications", unread_only=True)
    except Exception:
        logger.exception("query_unread_notification_count failed")
        raise


# ── Persistence + delivery / SSE bridge (API + Product ABI)


def find_notification(
    notif_type: str,
    title: str | None = None,
    *,
    dedup_key: str | None = None,
    kernel: Any = None,
) -> Any:
    from app.core.runtime.notification_bridge import find_notification as _find

    return _find(notif_type, title, dedup_key=dedup_key, kernel=kernel)


def create_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    related_id: str | None = None,
    related_type: str | None = None,
    dedup_key: str | None = None,
    actor: str = "system",
    kernel: Any = None,
) -> Any:
    from app.core.runtime.notification_bridge import create_notification as _create

    return _create(
        notif_type,
        title,
        content,
        related_id=related_id,
        related_type=related_type,
        dedup_key=dedup_key,
        actor=actor,
        kernel=kernel,
    )


def push_notification(
    notif_type: str,
    title: str,
    content: str,
    **kwargs: Any,
) -> Any:
    from app.core.runtime.notification_bridge import push_notification as _push

    return _push(notif_type, title, content, **kwargs)


def register_sse_queue(correlation_id: str) -> Any:
    from app.core.runtime.notification_bridge import register

    return register(correlation_id)


def unregister_sse_queue(correlation_id: str) -> None:
    from app.core.runtime.notification_bridge import unregister

    unregister(correlation_id)

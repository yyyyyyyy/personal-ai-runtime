"""Bridge sync Kernel code to async WebSocket notification broadcast.

Owns notification **persistence helpers** (``create_notification`` /
``find_notification``) plus transport:

- :func:`push_notification` — persists a notification row AND broadcasts it
- :func:`broadcast_event` — broadcast without persisting

Product / API should prefer Ports ABI re-exports (``read_ports`` /
``app.product.notifications``) rather than importing this module deeply.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict, cast

from app.core.runtime.kernel.constants import (
    AGGREGATE_NOTIFICATION,
    EVENT_NOTIFICATION_CREATED,
    EVENT_NOTIFICATION_UPDATED,
)

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel

logger = logging.getLogger(__name__)

# Main asyncio loop registered by RuntimeLoop so sync callers (Kernel emit
# paths) can schedule broadcasts without asyncio.run on a worker thread.
_broadcast_loop: asyncio.AbstractEventLoop | None = None
_PENDING_BROADCASTS: set[asyncio.Task] = set()


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
    if k is not None:
        return k
    from app.core.runtime.kernel_instance import kernel as default_kernel

    return default_kernel


def find_notification(
    notif_type: str,
    title: str | None = None,
    *,
    dedup_key: str | None = None,
    kernel: "Kernel | None" = None,
) -> NotificationPayload | None:
    """Return an existing notification by dedup_key or type+title, if any."""
    query_title = None if dedup_key is not None else title
    if kernel is None:
        from app.core.runtime import read_ports

        rows = read_ports.query_notifications(
            type=notif_type,
            limit=1,
            dedup_key=dedup_key,
            title=query_title,
        )
    else:
        filters: dict[str, Any] = {"type": notif_type, "limit": 1}
        if dedup_key is not None:
            filters["dedup_key"] = dedup_key
        elif title is not None:
            filters["title"] = title
        rows = kernel.query_state("notifications", **filters)
    if not rows:
        return None
    return cast(NotificationPayload, rows[0])


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
    """Create a notification and return it (idempotent by dedup_key or type + title)."""
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


def set_broadcast_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Register (or clear) the process main event loop for sync broadcasts."""
    global _broadcast_loop
    _broadcast_loop = loop


def push_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    kernel: "Kernel | None" = None,
) -> dict:
    """Persist a notification row and broadcast it to WebSocket clients.

    The WS envelope always uses ``type="notification"`` so the frontend can
    distinguish user-facing notifications from transport hints like
    ``memory_changed``. The domain category is carried as ``notification_type``.

    ``kernel`` lets callers that already hold a Kernel instance (e.g.
    reactions invoked via ``evaluate_cycle``) avoid the module-level default,
    which may point at a stale reference in tests that monkeypatch
    ``kernel_instance.kernel`` after this module was imported.
    """
    notif = create_notification(notif_type, title, content, kernel=kernel)
    payload = dict(notif)
    broadcast_event({
        **payload,
        "type": "notification",
        "notification_type": payload.get("type", notif_type),
    })
    return payload


def broadcast_event(event: dict) -> None:
    """Broadcast an arbitrary event payload to WebSocket clients.

    Pure transport — does NOT persist any row. See module docstring for the
    async/sync dispatch contract shared with :func:`push_notification`.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(_broadcast(event))
        _PENDING_BROADCASTS.add(task)
        task.add_done_callback(_PENDING_BROADCASTS.discard)
        return

    bound = _broadcast_loop
    if bound is not None and bound.is_running():
        try:
            fut = asyncio.run_coroutine_threadsafe(_broadcast(event), bound)
            fut.result(timeout=5.0)
        except Exception:
            logger.warning(
                "broadcast_event failed via bound loop for %s",
                event.get("type"),
                exc_info=True,
            )
        return

    try:
        asyncio.run(_broadcast(event))
    except Exception:
        logger.warning(
            "broadcast_event failed in sync context for %s",
            event.get("type"),
            exc_info=True,
        )


async def _broadcast(event: dict) -> None:
    try:
        from app.main import broadcast_notification
        await broadcast_notification(event)
    except Exception:
        logger.warning(
            "broadcast_notification failed for %s",
            event.get("type"),
            exc_info=True,
        )


# ── SSE queue registry (folded from sse_queue_registry.py) ────────────────

_registry: dict[str, asyncio.Queue] = {}


def register(correlation_id: str) -> asyncio.Queue:
    """Create and register a queue for the given correlation_id.

    Returns the queue so the SSE consumer can `async for` items.
    """
    q: asyncio.Queue[dict] = asyncio.Queue()
    _registry[correlation_id] = q
    return q


def unregister(correlation_id: str) -> None:
    """Remove a queue from the registry (call after SSE stream ends)."""
    _registry.pop(correlation_id, None)


async def push(correlation_id: str, payload: dict) -> None:
    """Push a text delta payload to the queue for the given correlation_id.

    If the queue doesn't exist (SSE consumer already disconnected), silently drop.
    """
    q = _registry.get(correlation_id)
    if q is None:
        return
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        logger.warning("SSE queue full for %s, dropping delta", correlation_id)


def reset_sse_queues() -> None:
    """Clear the in-memory SSE queue registry (test isolation)."""
    _registry.clear()
    set_broadcast_loop(None)

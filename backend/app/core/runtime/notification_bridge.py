"""Bridge sync Kernel code to async WebSocket notification broadcast.

Two public entry points share a single transport core:

- :func:`push_notification` — persists a notification row AND broadcasts it
  (used for user-facing notifications: morning brief, approval reminders…).
- :func:`broadcast_event` — broadcasts an arbitrary payload WITHOUT
  persisting (pure transport; used for cache-invalidation hints such as
  ``memory_changed`` that piggy-back on an already-persisted Kernel event).

Both functions are sync-callable from Kernel Space. Their async/sync
behaviour is intentionally identical so call sites can reason about them
without inspecting which context they happen to run in:

- **Async context (running event loop)**: schedule ``_broadcast`` as a
  fire-and-forget task on the current loop. Returns immediately.
- **Sync context (no running loop)**: run ``_broadcast`` to completion via
  ``asyncio.run``. This blocks the caller briefly but guarantees delivery.

The two branches diverge only in *when* the WebSocket write happens, not in
*whether*. Failures inside ``_broadcast`` are always swallowed at DEBUG —
transport must never roll back governed storage.
"""

from __future__ import annotations

import asyncio
import logging

from app.product.notifications import create_notification

logger = logging.getLogger(__name__)


def push_notification(notif_type: str, title: str, content: str) -> dict:
    """Persist a notification row and broadcast it to WebSocket clients.

    The WS envelope always uses ``type="notification"`` so the frontend can
    distinguish user-facing notifications from transport hints like
    ``memory_changed``. The domain category is carried as ``notification_type``.
    """
    notif = create_notification(notif_type, title, content)
    broadcast_event({
        **notif,
        "type": "notification",
        "notification_type": notif.get("type", notif_type),
    })
    return notif


def broadcast_event(event: dict) -> None:
    """Broadcast an arbitrary event payload to WebSocket clients.

    Pure transport — does NOT persist any row. See module docstring for the
    async/sync dispatch contract shared with :func:`push_notification`.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Sync context: run to completion so delivery is deterministic.
        # This is the path taken by tests and by fire-and-forget extractors
        # invoked outside an event loop.
        try:
            asyncio.run(_broadcast(event))
        except Exception:
            logger.debug(
                "broadcast_event failed in sync context for %s",
                event.get("type"),
                exc_info=True,
            )
        return

    # Async context: fire-and-forget on the running loop. Hold a strong
    # reference on the loop's default executor context by attaching the
    # task to a module-level set so it isn't garbage-collected before
    # completion ("task was destroyed but it is pending" warning).
    loop = asyncio.get_running_loop()
    task = loop.create_task(_broadcast(event))
    _PENDING_BROADCASTS.add(task)
    task.add_done_callback(_PENDING_BROADCASTS.discard)


_PENDING_BROADCASTS: set[asyncio.Task] = set()


async def _broadcast(event: dict) -> None:
    try:
        from app.main import broadcast_notification
        await broadcast_notification(event)
    except Exception:
        logger.debug(
            "broadcast_notification failed for %s",
            event.get("type"),
            exc_info=True,
        )

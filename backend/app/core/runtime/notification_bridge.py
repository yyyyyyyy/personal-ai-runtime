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
- **Bound main loop** (set via :func:`set_broadcast_loop`, typically by
  ``RuntimeLoop.start``): schedule onto that loop from sync threads via
  ``run_coroutine_threadsafe`` — avoids a nested ``asyncio.run``.
- **Sync context (no loop at all)**: run ``_broadcast`` to completion via
  ``asyncio.run``. Prefer calling from an async context when possible.

Failures inside ``_broadcast`` are logged at WARNING and never raised —
transport must never roll back governed storage.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.product.notifications import create_notification

if TYPE_CHECKING:
    from app.core.runtime.kernel import Kernel

logger = logging.getLogger(__name__)

# Main asyncio loop registered by RuntimeLoop so sync callers (Kernel emit
# paths) can schedule broadcasts without asyncio.run on a worker thread.
_broadcast_loop: asyncio.AbstractEventLoop | None = None
_PENDING_BROADCASTS: set[asyncio.Task] = set()


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

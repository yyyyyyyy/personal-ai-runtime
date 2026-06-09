"""Bridge sync scheduler code to async WebSocket notification broadcast."""

from __future__ import annotations

import asyncio
import logging

from app.product.notifications import create_notification

logger = logging.getLogger(__name__)


def push_notification(notif_type: str, title: str, content: str) -> dict:
    """Create DB notification and broadcast to WebSocket clients."""
    notif = create_notification(notif_type, title, content)
    event = {"type": "notification", **notif}
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast(event))
    except RuntimeError:
        try:
            asyncio.run(_broadcast(event))
        except Exception:
            logger.debug("No event loop for notification broadcast", exc_info=True)
    return notif


async def _broadcast(event: dict) -> None:
    try:
        from app.main import broadcast_notification
        await broadcast_notification(event)
    except Exception:
        logger.debug("broadcast_notification failed", exc_info=True)

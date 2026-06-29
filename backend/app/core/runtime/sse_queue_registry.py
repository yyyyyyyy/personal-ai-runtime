"""SSE Queue Registry — in-memory push channel for chat streaming.

ChatTextDelta events are too high-frequency for event_log (hundreds per turn).
This registry provides an asyncio.Queue per correlation_id so the ChatHandler
can push text deltas directly to the SSE stream without writing to event_log.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

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

"""HandlerRegistry — maps event types to business-logic handlers (Lane A).

Fan-out: one event type may register N handlers. The Scheduler creates one
ScheduledExecution per handler. Handlers are never silently overwritten.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from .execution import ExecutionContext
    from .kernel.event import Event

logger = logging.getLogger(__name__)

Handler = Callable[["ExecutionContext", "Event"], Awaitable[None]]

_registry: dict[str, list[Handler]] = {}


def subscribe(*event_types: str):
    """Decorator: append a handler for one or more event types (fan-out)."""

    def deco(fn: Handler) -> Handler:
        for et in event_types:
            bucket = _registry.setdefault(et, [])
            if any(h is fn or h.__name__ == fn.__name__ for h in bucket):
                logger.warning(
                    "HandlerRegistry: %s already listed for %s; skipping duplicate.",
                    fn.__name__,
                    et,
                )
                continue
            bucket.append(fn)
        return fn

    return deco


def get_handlers(event_type: str) -> list[Handler]:
    """Return all handlers registered for an event type (may be empty)."""
    return list(_registry.get(event_type, []))


def get_handler_named(event_type: str, handler_name: str) -> Handler | None:
    """Resolve a specific handler by function name for a ScheduledExecution."""
    for handler in get_handlers(event_type):
        if handler.__name__ == handler_name:
            return handler
    return None


def registered_types() -> list[str]:
    """Return all registered event types (for debugging / introspection)."""
    return sorted(_registry.keys())


def reset_handlers() -> None:
    """Clear all registered handlers — for test isolation."""
    _registry.clear()

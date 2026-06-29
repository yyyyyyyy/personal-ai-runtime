"""HandlerRegistry — maps event types to business-logic handlers.

The HandlerRegistry is the separation point between the Runtime (lifecycle,
state, subscriptions, checkpoint) and business logic (what happens when a
specific event arrives).

    Runtime Process        |  Business Logic
    -----------------------+------------------
    subscription           |  @subscribe("TaskCreated")
    dispatch(event)        |  async def on_task_created(instance, event)
    state view             |
    checkpoint             |

A Handler is a plain async function: (AgentInstance, Event) → None.
It does NOT know about routing — the Runtime dispatches events to it.

Handlers can be assembled dynamically onto different RuntimeProcess
configurations. The same TaskCompletedHandler can run on a Planner
process AND a Reviewer process without code duplication.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from .execution_context import ExecutionContext
    from .kernel.event import Event

logger = logging.getLogger(__name__)

Handler = Callable[["ExecutionContext", "Event"], Awaitable[None]]

_registry: dict[str, Handler] = {}


def subscribe(*event_types: str):
    """Decorator: register a handler function for one or more event types.

    Usage:

        @subscribe("TaskCreated")
        async def on_task_created(instance, event):
            ...

        @subscribe("TaskCreated", "TaskCompleted")
        async def handle_all_tasks(instance, event):
            ...

    The decorated function is registered in the global HandlerRegistry.
    The Runtime dispatches events to it by event.type — the handler
    never needs to check event.type itself.
    """
    def deco(fn: Handler) -> Handler:
        for et in event_types:
            if et in _registry:
                logger.warning(
                    "HandlerRegistry: %s is already registered for %s; overwriting.",
                    et, _registry[et].__name__,
                )
            _registry[et] = fn
        return fn
    return deco


def get_handler(event_type: str) -> Handler | None:
    """Look up the handler for an event type. Returns None if unregistered."""
    return _registry.get(event_type)


def registered_types() -> list[str]:
    """Return all registered event types (for debugging / introspection)."""
    return sorted(_registry.keys())

"""Event Bus — unified publish/subscribe event system.

All modules communicate through events, not direct calls.
Supports async handlers via asyncio.Queue.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    """Publish/subscribe event bus backed by asyncio.Queue.

    Events are typed strings (e.g. 'MessageReceived', 'GoalCreated').
    Handlers are async callables that receive (event_type, payload).
    """

    def __init__(self):
        self._subscribers: dict[str, list[Handler]] = {}
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._running = False
        self._worker_task: asyncio.Task | None = None

    def subscribe(self, event_type: str, handler: Handler):
        """Subscribe a handler to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler):
        """Unsubscribe a handler."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    def publish(self, event_type: str, payload: dict[str, Any] | None = None):
        """Publish an event to the bus (non-blocking)."""
        self._queue.put_nowait((event_type, payload or {}))

    async def start(self):
        """Start the event processing worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())

    async def stop(self):
        """Stop the event processing worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _process_events(self):
        """Worker that processes events from the queue."""
        while self._running:
            try:
                event_type, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event_type, payload)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"EventBus dispatch error: {e}")

    async def _dispatch(self, event_type: str, payload: dict[str, Any]):
        """Dispatch an event to all subscribed handlers."""
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_type, payload)
            except Exception as e:
                logger.error(f"Handler error for event '{event_type}': {e}")


# Pre-defined event types
class EventType:
    MESSAGE_RECEIVED = "MessageReceived"
    GOAL_CREATED = "GoalCreated"
    GOAL_COMPLETED = "GoalCompleted"
    TASK_CREATED = "TaskCreated"
    TASK_COMPLETED = "TaskCompleted"
    TASK_FAILED = "TaskFailed"
    STATE_TRANSITION = "StateTransition"
    APPROVAL_REQUESTED = "ApprovalRequested"
    APPROVAL_RESOLVED = "ApprovalResolved"
    SUGGESTION_GENERATED = "SuggestionGenerated"
    SCHEDULE_TRIGGERED = "ScheduleTriggered"


# Global singleton
event_bus = EventBus()

"""Event bus dispatch + submit_command Future resolution.

Extracted from ``kernel.py`` so the God Object LOC budget can shrink without
growing ``runtime_files`` (paired with folding ``projectors_timer`` into
``projectors_inbox``). Kernel Space still owns this module.

``submit_command`` is NOT a new Ontology layer — it is a synchronous wrapper
around ``emit_event`` that awaits a matching completion event via
correlation_id.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .event import Event

logger = logging.getLogger(__name__)


def log_dispatch_task_exception(task: "asyncio.Task") -> None:
    """Done callback for fire-and-forget Event dispatch tasks.

    Without this, exceptions inside async dispatchers live only in the
    task's _exception attribute and are never logged — making production
    debugging nearly impossible.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Event dispatch task failed: %s",
            exc,
            exc_info=exc,
        )


def default_completion_type(event_type: str) -> str:
    """Derive the completion event type for a submit_command request."""
    if event_type.endswith("Requested"):
        return event_type.replace("Requested", "Completed")
    return event_type + "Completed"


def resolve_pending_command(
    kernel: Any,
    *,
    correlation_id: str,
    completion_type: str,
    payload: dict[str, object],
    aggregate_type: str = "command",
    aggregate_id: str = "rejected",
    caused_by: str | None = None,
) -> bool:
    """Resolve a waiting ``submit_command`` Future without emitting a domain event.

    Used when Lane A rejects dispatch under backpressure so callers get
    ``{"status": "error", "error": "queue_full"}`` instead of timing out.
    Returns True when a pending Future was resolved.
    """
    if not correlation_id or not completion_type:
        return False
    key = (correlation_id, completion_type)
    with kernel._commands_lock:
        future = kernel._pending_commands.get(key)
    if future is None:
        return False

    from .event import Event

    synthetic = Event(
        type=completion_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        actor="scheduler",
        caused_by=caused_by,
        correlation_id=correlation_id,
    )
    if not _resolve_future_threadsafe(future, synthetic):
        return False
    with kernel._commands_lock:
        kernel._pending_commands.pop(key, None)
    return True


async def submit_command(
    kernel: Any,
    type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, object] | None = None,
    actor: str = "system",
    caused_by: str | None = None,
    correlation_id: str | None = None,
    *,
    timeout: float = 60.0,
    completion_type: str | None = None,
) -> dict:
    """Emit an event and wait for a completion event synchronously.

    Returns the completion event's payload dict, or
    ``{"error": "timeout", "status": "timeout"}``.
    """
    if correlation_id is None:
        correlation_id = f"cmd_{uuid.uuid4().hex[:12]}"

    if completion_type is None:
        completion_type = default_completion_type(type)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    key = (correlation_id, completion_type)
    with kernel._commands_lock:
        kernel._pending_commands[key] = future

    try:
        kernel.emit_event(
            type=type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            actor=actor,
            caused_by=caused_by,
            correlation_id=correlation_id,
        )

        result = await asyncio.wait_for(future, timeout=timeout)
        return result.payload
    except asyncio.TimeoutError:
        return {"error": "timeout", "status": "timeout"}
    except Exception as exc:
        return {"error": str(exc), "status": "error"}
    finally:
        # Defensive cleanup: guarantee the registration never leaks even
        # if dispatch misses the completion event. pop(key, None) is a
        # safe no-op when dispatch already resolved and removed the key.
        with kernel._commands_lock:
            kernel._pending_commands.pop(key, None)


def _resolve_future_threadsafe(
    future: "asyncio.Future",
    event: "Event",
) -> bool:
    """Schedule ``future.set_result(event)`` on the running loop.

    Returns False when no loop is running (caller should leave the future
    to time out — do NOT cancel, which injects CancelledError into wait_for).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    def _resolve(f: "asyncio.Future", e: "Event") -> None:
        if not f.done():
            f.set_result(e)

    loop.call_soon_threadsafe(_resolve, future, event)
    return True


def dispatch(kernel: Any, event: "Event") -> None:
    """Push event to sync subscribers, async dispatcher, and command Futures."""
    for flt, handler in list(kernel._subscribers):
        if flt["type"] and flt["type"] != event.type:
            continue
        if flt["aggregate_type"] and flt["aggregate_type"] != event.aggregate_type:
            continue
        try:
            handler(event)
        except Exception as exc:
            logger.warning(
                "Event subscriber failed for %s (aggregate=%s/%s): %s",
                event.type,
                event.aggregate_type,
                event.aggregate_id,
                exc,
                exc_info=True,
            )

    # Fire registered async dispatcher (Scheduler). Storage has already
    # committed; this is best-effort live delivery.
    async_dispatcher: Callable | None = kernel._async_dispatcher
    if async_dispatcher is not None:
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(async_dispatcher(event))
            task.add_done_callback(log_dispatch_task_exception)
            if not hasattr(kernel, "_dispatch_tasks"):
                kernel._dispatch_tasks = set()
            task.add_done_callback(kernel._dispatch_tasks.discard)
            kernel._dispatch_tasks.add(task)
        except RuntimeError:
            logger.debug(
                "Event dispatch skipped (no running loop) for %s "
                "aggregate=%s/%s — event is persisted, subscribers "
                "will see it on next read_events/replay.",
                event.type,
                event.aggregate_type,
                event.aggregate_id,
            )

    # Resolve pending submit_command Futures on matching completion events.
    key = (event.correlation_id or "", event.type)
    with kernel._commands_lock:
        future = kernel._pending_commands.pop(key, None)
    if future is not None and not future.done():
        if not _resolve_future_threadsafe(future, event):
            return

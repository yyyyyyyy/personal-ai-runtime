"""Bridge Kernel event_log stream to asyncio EventBus (transport only)."""

from __future__ import annotations

from typing import Callable

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel.event import Event
from app.core.runtime.kernel_instance import kernel

_KERNEL_TO_BUS: dict[str, str] = {
    "TaskCreated": EventType.TASK_CREATED,
    "TaskCompleted": EventType.TASK_COMPLETED,
    "TaskFailed": EventType.TASK_FAILED,
    "ApprovalRequested": EventType.APPROVAL_REQUESTED,
    "ApprovalGranted": EventType.APPROVAL_RESOLVED,
    "ApprovalDenied": EventType.APPROVAL_RESOLVED,
}


def _bus_payload(event: Event) -> dict:
    p = event.payload or {}
    if event.type == "TaskCreated":
        return {
            "task_id": event.aggregate_id,
            "name": p.get("name", ""),
            "parent_goal_id": p.get("parent_goal_id"),
            "parent_task_id": p.get("parent_task_id"),
        }
    if event.type in ("TaskCompleted", "TaskFailed"):
        return {"task_id": event.aggregate_id, "name": p.get("name", ""), **p}
    if event.type == "TaskStatusChanged":
        return {"task_id": event.aggregate_id, "name": p.get("name", ""), "status": p.get("status")}
    if event.type == "ApprovalRequested":
        return {
            "approval_id": event.aggregate_id,
            "action": p.get("action", ""),
            "params": p.get("ctx", {}).get("args", {}),
            "task_id": p.get("ctx", {}).get("task_id"),
        }
    if event.type == "ApprovalGranted":
        return {
            "approval_id": event.aggregate_id,
            "status": "approved",
            "reason": p.get("reason", ""),
            "action": p.get("action", ""),
        }
    if event.type == "ApprovalDenied":
        return {
            "approval_id": event.aggregate_id,
            "status": "denied",
            "reason": p.get("reason", ""),
            "action": p.get("action", ""),
        }
    return dict(p)


def _on_kernel_event(event: Event) -> None:
    bus_type = _KERNEL_TO_BUS.get(event.type)
    if event.type == "TaskStatusChanged":
        status = (event.payload or {}).get("status")
        if status == "completed":
            bus_type = EventType.TASK_COMPLETED
        elif status == "failed":
            bus_type = EventType.TASK_FAILED
    if bus_type is None:
        return
    event_bus.publish(bus_type, _bus_payload(event))


_bridge_unsubscribe: Callable[[], None] | None = None


def register_kernel_event_bridge() -> None:
    """Subscribe Kernel event stream and forward governed lifecycle events to the bus."""
    global _bridge_unsubscribe
    if _bridge_unsubscribe is not None:
        return
    _bridge_unsubscribe = kernel.subscribe_events(_on_kernel_event)


def unregister_kernel_event_bridge() -> None:
    global _bridge_unsubscribe
    if _bridge_unsubscribe is not None:
        _bridge_unsubscribe()
        _bridge_unsubscribe = None

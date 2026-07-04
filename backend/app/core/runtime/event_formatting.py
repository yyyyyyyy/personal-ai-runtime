"""Event formatting — convert kernel Events to API/UI-friendly dicts.

The `events` APP_STORAGE table (formerly the legacy event store) is retained
for backward compatibility. This module formats event_log entries for UI
consumers that still expect the old shape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel.event import Event

_LEGACY_TYPE: dict[str, str] = {
    "GoalCreated": "goal_created",
    "GoalUpdated": "goal_status_changed",
    "GoalCompleted": "goal_status_changed",
    "GoalDeleted": "goal_deleted",
    "ActionCreated": "action_created",
    "ActionUpdated": "action_status_changed",
    "ActionDeleted": "action_deleted",
    "WorkItemCreated": "task_created",
    "WorkItemUpdated": "task_status_changed",
    "WorkItemStatusChanged": "task_status_changed",
    "WorkItemDeleted": "task_status_changed",
    "CapabilityInvoked": "tool_call",
    "ApprovalRequested": "approval_requested",
    "ApprovalGranted": "approval_granted",
    "ApprovalDenied": "approval_denied",
    "TaskCreated": "task_created",
    "TaskCompleted": "task_completed",
    "TaskFailed": "task_failed",
    "TaskStatusChanged": "task_status_changed",
    "MemoryDerived": "memory_derived",
    "ConversationRecorded": "conversation",
}


def _goal_id_for(event: Event) -> str | None:
    """Extract goal_id from an event's aggregate or payload."""
    if event.aggregate_type == "goal":
        return event.aggregate_id
    if event.aggregate_type in ("action", "work_item"):
        return event.payload.get("goal_id") or event.payload.get("parent_goal_id")
    return event.payload.get("goal_id")


def _summary_for(event: Event) -> str:
    """Generate a human-readable summary string for an event."""
    p = event.payload
    t = event.type
    if t == "GoalCreated":
        return f"Goal created: {p.get('title', '')}"
    if t in ("GoalUpdated", "GoalCompleted"):
        return f"Goal status -> {p.get('status', t)}"
    if t == "ActionCreated":
        return f"Action created: {p.get('title', '')}"
    if t == "ActionUpdated":
        return f"Action status -> {p.get('status', '')}"
    if t == "CapabilityInvoked":
        return f"Tool called: {p.get('name', '')}"
    if t == "ApprovalRequested":
        return f"Approval requested: {p.get('action', '')}"
    if t == "ApprovalGranted":
        return f"Approval granted: {p.get('action', '')}"
    if t == "ApprovalDenied":
        return f"Approval denied: {p.get('action', '')}"
    if t == "TaskCreated":
        return f"Task created: {p.get('name', '')}"
    if t in ("TaskCompleted", "TaskFailed", "TaskStatusChanged"):
        return f"Task {p.get('status', t)}: {event.aggregate_id}"
    if t == "WorkItemCreated":
        return f"WorkItem created: {p.get('title', '')}"
    if t in ("WorkItemStatusChanged", "WorkItemUpdated"):
        return f"WorkItem {p.get('status', t)}: {event.aggregate_id}"
    if t == "MemoryDerived":
        return f"Memory derived: {str(p.get('content', ''))[:60]}"
    if t == "ConversationRecorded":
        return f"Conversation: {str(p.get('user_message', ''))[:60]}"
    return f"{t}: {event.aggregate_id}"


def to_legacy_dict(event: Event) -> dict:
    """Convert a Kernel Event to a UI-friendly dict shape."""
    legacy_type = _LEGACY_TYPE.get(event.type, event.type.lower())
    payload = event.payload or {}
    return {
        "id": event.id,
        "type": legacy_type,
        "summary": _summary_for(event),
        "goal_id": _goal_id_for(event),
        "payload": json.dumps(payload) if payload else None,
        "timestamp": event.ts,
    }


def goal_events(goal_id: str, *, limit: int = 20) -> list[dict]:
    """Return goal-scoped events from event_log (goal + related actions/work_items)."""
    from app.core.runtime.kernel_instance import kernel

    goal_ev = kernel.read_events(
        aggregate_type="goal", aggregate_id=goal_id, order="desc", limit=limit,
    )
    action_ev = kernel.read_events(
        aggregate_type="action", payload_goal_id=goal_id,
        order="desc", limit=limit,
    )
    work_item_ev = kernel.read_events(
        aggregate_type="work_item", payload_goal_id=goal_id,
        order="desc", limit=limit,
    )
    combined = sorted(goal_ev + action_ev + work_item_ev, key=lambda e: e.seq or 0, reverse=True)[:limit]
    return [to_legacy_dict(e) for e in combined]


def recent_events(
    read_fn,
    *,
    days: int = 7,
    limit: int = 50,
    event_type: str | None = None,
    goal_id: str | None = None,
) -> list[dict]:
    """Read recent events from event_log and return UI-friendly rows."""
    since_ts = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    filters: dict = {"since_ts": since_ts, "limit": limit, "order": "desc"}
    if event_type:
        filters["type"] = event_type

    events = read_fn(**filters)
    rows = [to_legacy_dict(e) for e in events]

    if goal_id:
        rows = [r for r in rows if r.get("goal_id") == goal_id]

    return rows[:limit]

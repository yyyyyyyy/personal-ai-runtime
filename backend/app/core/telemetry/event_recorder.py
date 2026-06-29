"""Event Recorder — records application-layer events via kernel event_log (C1: migrated from legacy events table).

All reads and writes go through kernel.emit_event / kernel.read_events.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.activity_log import log_activity


@dataclass
class Event:
    """A system event representing a user action or system occurrence."""

    type: str
    summary: str
    goal_id: str | None = None
    payload: dict[str, Any] | None = None


def _kernel():
    from app.core.runtime.kernel_instance import kernel
    return kernel


def _event_to_row(event, *, event_type_hint: str = "") -> dict:
    """Convert a kernel event_log entry back to legacy events-table row shape."""
    p = event.payload or {}
    return {
        "id": event.id,
        "type": event.type,
        "summary": p.get("summary", ""),
        "goal_id": p.get("goal_id"),
        "payload": json.dumps({k: v for k, v in p.items() if k not in ("summary", "goal_id")}),
        "timestamp": event.ts,
    }


class EventRecorder:
    """Records typed events via kernel event_log (replaces legacy events table)."""

    def record(self, event: Event) -> str:
        """Record an event via kernel.emit_event and return its ID."""
        event_id = str(uuid.uuid4())

        payload = event.payload or {}
        payload["summary"] = event.summary
        if event.goal_id:
            payload["goal_id"] = event.goal_id

        _kernel().emit_event(
            type=event.type,
            aggregate_type="event",
            aggregate_id=event_id,
            payload=payload,
            actor="system",
        )

        log_activity(
            f"event.{event.type}",
            {"event_id": event_id, "summary": event.summary, "goal_id": event.goal_id},
        )

        return event_id

    def get_recent_events(self, days: int = 7, limit: int = 50) -> list[dict]:
        """Get recent events from event_log within the specified time window."""

        since_ts = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        events = _kernel().read_events(
            aggregate_type="event",
            since_ts=since_ts,
            limit=limit,
            order="desc",
        )
        return [_event_to_row(e) for e in events]

    def get_events_by_type(self, event_type: str, limit: int = 20) -> list[dict]:
        """Get events of a specific type from event_log."""
        events = _kernel().read_events(
            type=event_type,
            limit=limit,
            order="desc",
        )
        return [_event_to_row(e) for e in events]

    def get_events_for_goal(self, goal_id: str, limit: int = 20) -> list[dict]:
        """Get events related to a specific goal from event_log."""
        events = _kernel().read_events(
            aggregate_type="event",
            payload_goal_id=goal_id,
            limit=limit,
            order="desc",
        )
        return [_event_to_row(e) for e in events]


event_recorder = EventRecorder()

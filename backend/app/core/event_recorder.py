"""Event Recorder — records user actions and system events for later analysis.

Events feed into the Memory Engine (for memory extraction) and Review Engine (for insights).
"""

import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Any

from app.store.database import db
from app.activity_log import log_activity


@dataclass
class Event:
    """A system event representing a user action or system occurrence."""

    type: str
    summary: str
    goal_id: str | None = None
    payload: dict[str, Any] | None = None


class EventRecorder:
    """Records typed events to SQLite for later retrieval and analysis."""

    def record(self, event: Event) -> str:
        """Record an event and return its ID."""
        event_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO events (id, type, summary, goal_id, payload, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    event.type,
                    event.summary,
                    event.goal_id,
                    json.dumps(event.payload) if event.payload else None,
                    now,
                ),
            )

        # Also log to activity log for auditing
        log_activity(
            f"event.{event.type}",
            {"event_id": event_id, "summary": event.summary, "goal_id": event.goal_id},
        )

        return event_id

    def get_recent_events(self, days: int = 7, limit: int = 50) -> list[dict]:
        """Get recent events within the specified time window."""
        with db.get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM events 
                   WHERE timestamp >= datetime('now', ?) 
                   ORDER BY timestamp DESC LIMIT ?""",
                (f"-{days} days", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events_by_type(self, event_type: str, limit: int = 20) -> list[dict]:
        """Get events of a specific type."""
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events_for_goal(self, goal_id: str, limit: int = 20) -> list[dict]:
        """Get events related to a specific goal."""
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE goal_id = ? ORDER BY timestamp DESC LIMIT ?",
                (goal_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


event_recorder = EventRecorder()

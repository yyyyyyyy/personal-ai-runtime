"""World Model — maintains a 30-day rolling snapshot of the user's life state.

Aggregates events, goals, memories, and external data into a structured context.
Injected into Planner's system prompt on every call.
"""

import json
from datetime import datetime, timedelta

from app.store.database import db


class WorldModel:
    """30-day rolling user life snapshot for context injection."""

    def __init__(self):
        self._cached_snapshot: dict | None = None

    def refresh_snapshot(self) -> dict:
        self._cached_snapshot = self.build_snapshot()
        return self._cached_snapshot

    def get_snapshot(self) -> dict:
        if self._cached_snapshot is None:
            self._cached_snapshot = self.build_snapshot()
        return self._cached_snapshot

    def build_snapshot(self) -> dict:
        """Build the current world state snapshot."""
        now = datetime.utcnow()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        with db.get_db() as conn:
            active_goals = conn.execute(
                "SELECT title, status, deadline FROM goals WHERE status = 'active'"
            ).fetchall()

            recent_events = conn.execute(
                "SELECT type, summary, timestamp FROM events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 50",
                (thirty_days_ago,),
            ).fetchall()

            goal_count = conn.execute("SELECT COUNT(*) as c FROM goals").fetchone()["c"]
            completed_count = conn.execute(
                "SELECT COUNT(*) as c FROM goals WHERE status = 'completed' AND updated_at >= ?",
                (thirty_days_ago,),
            ).fetchone()["c"]

        events_by_type: dict[str, int] = {}
        for e in recent_events:
            t = dict(e)["type"]
            events_by_type[t] = events_by_type.get(t, 0) + 1

        return {
            "timestamp": now.isoformat(),
            "health": {
                "active_goals": len(active_goals),
                "completed_recently": completed_count,
                "total_goals": goal_count,
            },
            "work": {
                "goals_with_deadline": len([g for g in active_goals if dict(g).get("deadline")]),
                "recent_activity_types": events_by_type,
            },
            "summary": f"Active goals: {len(active_goals)}. " +
                       f"Completed recently: {completed_count}. " +
                       f"Recent events: {sum(events_by_type.values())}.",
        }

    def to_prompt_context(self) -> str:
        """Convert snapshot to a system prompt appendix."""
        snapshot = self.get_snapshot()

        lines = ["## Current Life Snapshot (last 30 days)"]
        lines.append(f"- Active Goals: {snapshot['health']['active_goals']}")
        lines.append(f"- Completed Goals (30d): {snapshot['health']['completed_recently']}")
        lines.append(f"- Recent Activity: {json.dumps(snapshot['work']['recent_activity_types'])}")
        return "\n".join(lines)


world_model = WorldModel()

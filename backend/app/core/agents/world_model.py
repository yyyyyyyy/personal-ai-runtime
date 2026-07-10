"""World Model — maintains a 30-day rolling snapshot of the user's life state.

Aggregates events, goals, memories, and external data into a structured context.
Injected into Planner's system prompt on every call.
"""

import json
from datetime import UTC, datetime, timedelta

from app.core.runtime.event_formatting import to_legacy_dict
from app.core.runtime.kernel_instance import kernel


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
        now = datetime.now(UTC)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        # v1.0 Phase 4: goals table retired — always read from work_items.
        active_goals = kernel.query_state(
            "work_items", work_type="goal", status="active", limit=500,
        )
        all_goals = kernel.query_state(
            "work_items", work_type="goal", limit=500,
        )
        completed_recently = kernel.query_state(
            "work_items", work_type="goal",
            status="completed", updated_since=thirty_days_ago, limit=500,
        )

        recent_kernel_events = kernel.read_events(
            since_ts=thirty_days_ago, limit=50, order="desc"
        )
        events_by_type: dict[str, int] = {}
        for e in recent_kernel_events:
            t = to_legacy_dict(e)["type"]
            events_by_type[t] = events_by_type.get(t, 0) + 1

        return {
            "timestamp": now.isoformat(),
            "health": {
                "active_goals": len(active_goals),
                "completed_recently": len(completed_recently),
                "total_goals": len(all_goals),
            },
            "work": {
                "goals_with_deadline": len([g for g in active_goals if g.get("deadline")]),
                "recent_activity_types": events_by_type,
            },
            "summary": f"Active goals: {len(active_goals)}. "
            + f"Completed recently: {len(completed_recently)}. "
            + f"Recent events: {sum(events_by_type.values())}.",
        }

    def to_prompt_context(self) -> str:
        """Convert snapshot to a system prompt appendix."""
        snapshot = self.get_snapshot()

        lines = ["## Current Life Snapshot (last 30 days)"]
        lines.append(f"- Active Goals: {snapshot['health']['active_goals']}")
        lines.append(f"- Completed Goals (30d): {snapshot['health']['completed_recently']}")
        lines.append(f"- Recent Activity: {json.dumps(snapshot['work']['recent_activity_types'])}")
        return "\n".join(lines)


from app.core.runtime.runtime_container import _LazyProxy, runtime  # noqa: E402

world_model = _LazyProxy(lambda: runtime.world_model)


def reset_world_model() -> None:
    """Clear the world model cache so the next read rebuilds (test isolation)."""
    runtime._world_model = None

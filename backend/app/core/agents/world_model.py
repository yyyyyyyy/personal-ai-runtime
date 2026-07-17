"""World Model — 30-day rolling snapshot for brief / planner context.

Chat turns use the Fragment Pipeline (goals / timeline / background), not this
module. ``to_prompt_context`` is consumed via ``read_ports.query_world_context``
(e.g. calendar/world fragment paths and Sunday cron warm-up).

Prompt reads always rebuild from governed projections so the snapshot is fresh;
``refresh_snapshot`` still warms an optional cache for non-prompt callers.
"""

import json
from datetime import UTC, datetime, timedelta

from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.read_ports import to_legacy_dict


class WorldModel:
    """30-day rolling user life snapshot for brief/planner context injection."""

    def __init__(self):
        self._cached_snapshot: dict | None = None

    def refresh_snapshot(self) -> dict:
        self._cached_snapshot = self.build_snapshot()
        return self._cached_snapshot

    def get_snapshot(self) -> dict:
        """Return a cached snapshot if warm, otherwise build once."""
        if self._cached_snapshot is None:
            self._cached_snapshot = self.build_snapshot()
        return self._cached_snapshot

    def build_snapshot(self) -> dict:
        """Build the current world state snapshot."""
        now = datetime.now(UTC)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        active_goals = read_ports.query_active_goals(limit=500)
        all_goals = read_ports.query_goals(limit=500)
        completed_recently = read_ports.query_completed_goals(
            updated_since=thirty_days_ago, limit=500,
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
        """Fresh snapshot rendered for LLM context (never serves a stale cache)."""
        snapshot = self.build_snapshot()
        self._cached_snapshot = snapshot

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

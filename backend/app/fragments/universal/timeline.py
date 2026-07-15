"""TimelineContextFragment — pending actions + recent events in one budget slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_PENDING_ACTION_LIMIT = 5
_EVENT_DAYS = 7
_EVENT_FETCH_LIMIT = 20
_EVENT_DISPLAY_LIMIT = 10


@dataclass
class TimelineContextFragment(ContextFragment):
    """Pending actions + recent events — unified timeline fragment."""

    id: str = field(default="core.timeline", init=False)
    priority: int = field(default=70, init=False)
    max_tokens: int = field(default=2000, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"timeline", "actions", "events", "universal"}), init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        parts: list[str] = []

        # ── Pending actions ──
        pending = read_ports.query_pending_actions(limit=_PENDING_ACTION_LIMIT)
        if pending:
            lines = ["## Pending Actions\n"]
            for action in pending[:_PENDING_ACTION_LIMIT]:
                status = action.get("status", "pending")
                title = action.get("title", "")
                lines.append(f"- [{status}] {title}")
            parts.append("\n".join(lines))

        # ── Recent events ──
        recent = read_ports.query_recent_legacy_events(days=_EVENT_DAYS, limit=_EVENT_FETCH_LIMIT)
        if recent:
            lines = ["## Recent Events\n"]
            for event in recent[:_EVENT_DISPLAY_LIMIT]:
                summary = event.get("summary", "")
                timestamp = event.get("timestamp", "")
                date_part = timestamp[:10] if timestamp else ""
                if date_part:
                    lines.append(f"- {summary} ({date_part})")
                else:
                    lines.append(f"- {summary}")
            parts.append("\n".join(lines))

        if not parts:
            return FragmentResult(content="")
        return FragmentResult(content="\n\n".join(parts))

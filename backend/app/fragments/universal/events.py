"""EventsContextFragment — recent runtime events for prompt compilation.

Read-only. Same window as legacy ContextEngine recent-events path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_EVENT_DAYS = 7
_EVENT_FETCH_LIMIT = 20
_EVENT_DISPLAY_LIMIT = 10


@dataclass
class EventsContextFragment(ContextFragment):
    """Surface recent events for prompt compilation."""

    id: str = field(default="core.events", init=False)
    priority: int = field(default=65, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"events", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        recent = read_ports.query_recent_legacy_events(days=_EVENT_DAYS, limit=_EVENT_FETCH_LIMIT)
        if not recent:
            return FragmentResult(content="")

        lines = ["## Recent Events\n"]
        for event in recent[:_EVENT_DISPLAY_LIMIT]:
            summary = event.get("summary", "")
            timestamp = event.get("timestamp", "")
            date_part = timestamp[:10] if timestamp else ""
            if date_part:
                lines.append(f"- {summary} ({date_part})")
            else:
                lines.append(f"- {summary}")
        return FragmentResult(content="\n".join(lines))

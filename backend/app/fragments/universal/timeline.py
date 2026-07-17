"""TimelineContextFragment — pending actions + recent events in one budget slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.agents.token_counter import count_text_tokens, truncate_to_token_budget
from app.core.runtime import read_ports

_EVENT_DAYS = 7
_RICH_TAGS = frozenset({"planning", "review", "goals"})
_NOISY_EVENT_TYPES = frozenset({"conversation", "tool_call", "memory_derived"})

_PENDING_LIMIT_DEFAULT = 3
_PENDING_LIMIT_RICH = 5
_EVENT_LIMIT_DEFAULT = 5
_EVENT_LIMIT_RICH = 7


def _deadline_date(raw: object) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _format_deadline(raw: object, *, today: date | None = None) -> str:
    d = _deadline_date(raw)
    if d is None:
        return ""
    day = today or date.today()
    if d < day:
        return f"截止 {d.isoformat()}·已逾期"
    if d == day:
        return f"截止 {d.isoformat()}·今天"
    return f"截止 {d.isoformat()}"


def _format_date(raw: object) -> str:
    text = str(raw or "").strip()
    return text[:10] if len(text) >= 10 else ""


def format_pending_action_line(row: dict, *, today: date | None = None) -> str:
    status = str(row.get("status") or "pending").strip() or "pending"
    title = str(row.get("title") or "").strip() or "无标题"
    work_type = str(row.get("work_type") or "").strip()
    tags = [status]
    if work_type and work_type != "action":
        tags.append(work_type)

    parts = [f"- [{'|'.join(tags)}] {title}"]
    deadline = _format_deadline(row.get("deadline"), today=today)
    if deadline:
        parts.append(deadline)
    return " · ".join(parts)


def format_event_line(event: dict) -> str:
    summary = str(event.get("summary") or "").strip() or "(无摘要)"
    date_part = _format_date(event.get("timestamp"))
    if date_part:
        return f"- {summary} ({date_part})"
    return f"- {summary}"


@dataclass
class TimelineContextFragment(ContextFragment):
    """Pending actions + recent events — unified timeline fragment."""

    id: str = field(default="core.timeline", init=False)
    priority: int = field(default=70, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"timeline", "actions", "events", "universal"}),
        init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        rich = bool(ctx.intent_tags & _RICH_TAGS)
        pending_limit = _PENDING_LIMIT_RICH if rich else _PENDING_LIMIT_DEFAULT
        event_limit = _EVENT_LIMIT_RICH if rich else _EVENT_LIMIT_DEFAULT

        pending_part = ""
        events_part = ""

        try:
            pending = read_ports.query_pending_actions(limit=pending_limit)
        except Exception:
            pending = []
        if pending:
            today = date.today()
            lines = ["## 待办动作\n"]
            lines.extend(format_pending_action_line(a, today=today) for a in pending)
            pending_part = "\n".join(lines)

        try:
            recent = read_ports.query_recent_legacy_events(
                days=_EVENT_DAYS,
                limit=event_limit,
            )
        except Exception:
            recent = []
        if recent:
            if not rich:
                filtered = [
                    e
                    for e in recent
                    if str(e.get("type") or "") not in _NOISY_EVENT_TYPES
                ]
                recent = filtered or recent
            lines = ["## 近期事件\n"]
            lines.extend(format_event_line(e) for e in recent[:event_limit])
            events_part = "\n".join(lines)

        parts = [p for p in (pending_part, events_part) if p]
        if not parts:
            return FragmentResult(content="")

        if len(parts) == 2:
            pending_tokens = count_text_tokens(parts[0])
            events_budget = max(0, self.max_tokens - pending_tokens)
            trimmed_events = truncate_to_token_budget(parts[1], events_budget)
            content = "\n\n".join(p for p in (parts[0], trimmed_events) if p)
        else:
            content = truncate_to_token_budget(parts[0], self.max_tokens)

        return FragmentResult(content=content)

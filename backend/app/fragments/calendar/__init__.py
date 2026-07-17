"""Calendar context fragments.

读取 OS 日历事件，无需专用存储表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


def _parse_start(raw: str) -> datetime | date | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _format_event_when(event: dict, *, mode: str) -> str:
    """Format event time for today agenda or upcoming list."""
    if event.get("all_day"):
        start = _parse_start(str(event.get("start") or event.get("date") or ""))
        if mode == "today":
            return "全天"
        return start.isoformat()[:10] if start else "全天"

    start = _parse_start(str(event.get("start") or ""))
    if isinstance(start, datetime):
        if mode == "today":
            return start.strftime("%H:%M")
        return start.strftime("%Y-%m-%d %H:%M")

    if isinstance(start, date):
        return start.isoformat() if mode == "week" else "全天"

    # Backward-compatible fallback for older payloads.
    legacy = str(event.get("date") or "").strip()
    if legacy:
        return legacy if mode == "week" else "全天"
    return "时间未定" if mode == "week" else "全天"


def _format_event_line(event: dict, *, mode: str) -> str:
    title = event.get("title") or "无标题"
    when = _format_event_when(event, mode=mode)
    location = f" @{event['location']}" if event.get("location") else ""
    return f"- {when}  {title}{location}"


def _event_sources(events: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for e in events:
        title = str(e.get("title") or "无标题")
        start = str(e.get("start") or e.get("date") or title)
        sources.append({"id": f"calendar:{start}:{title}", "type": "calendar", "title": title})
    return sources


@dataclass
class UpcomingEventsFragment(ContextFragment):
    """收集未来几天的日历事件。"""

    id: str = field(default="calendar.upcoming", init=False)
    priority: int = field(default=60, init=False)
    max_tokens: int = field(default=2000, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"calendar"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        try:
            data = read_ports.query_calendar_upcoming(days=7)
        except Exception:
            return FragmentResult(content="")

        events = data.get("events", [])
        if not events:
            return FragmentResult(content="未来一周暂无日程安排。")

        lines = ["## 未来日程\n"]
        lines.extend(_format_event_line(e, mode="week") for e in events)
        return FragmentResult(content="\n".join(lines), sources=_event_sources(events))


@dataclass
class DailyAgendaFragment(ContextFragment):
    """收集今天的议程（含日历助手角色定义，原 CalendarIdentityFragment 已合并）。"""

    id: str = field(default="calendar.today", init=False)
    priority: int = field(default=75, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"calendar"}), init=False)

    _IDENTITY = (
        "You are a Calendar assistant within the Personal AI Runtime.\n"
        "Scope: check events/agenda, resolve conflicts, remind commitments.\n"
        "Be time-aware, proactive, concise, and privacy-aware.\n"
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        try:
            data = read_ports.query_calendar_today_events()
        except Exception:
            return FragmentResult(content=self._IDENTITY)

        events = data.get("events", [])
        if not events:
            return FragmentResult(content=self._IDENTITY + "\n今日暂无日程安排。")

        lines = [self._IDENTITY, "## 今日日程\n"]
        lines.extend(_format_event_line(e, mode="today") for e in events)
        return FragmentResult(content="\n".join(lines), sources=_event_sources(events))

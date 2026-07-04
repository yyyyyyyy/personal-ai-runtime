"""Calendar context fragments.

读取 OS 日历事件，无需专用存储表。

v0.7.0: CalendarIdentityFragment 身份声明合并进 DailyAgendaFragment。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


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
        for e in events:
            title = e.get("title", "无标题")
            start = e.get("start", "")
            dt_str = start[:16] if start else "时间未定"
            lines.append(f"- {dt_str}  {title}")

        return FragmentResult(content="\n".join(lines))


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
            return FragmentResult(content=self._IDENTITY + "\n今日暂无日程安排。")

        events = data.get("events", [])
        if not events:
            return FragmentResult(content=self._IDENTITY + "\n今日暂无日程安排。")

        lines = [self._IDENTITY, "## 今日日程\n"]
        for e in events:
            title = e.get("title", "无标题")
            start = e.get("start", "")
            time_str = start[11:16] if start and len(start) >= 16 else "全天"
            location = f" @{e['location']}" if e.get("location") else ""
            lines.append(f"- {time_str}  {title}{location}")

        return FragmentResult(content="\n".join(lines))

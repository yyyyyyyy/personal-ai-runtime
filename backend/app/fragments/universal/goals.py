"""GoalsContextFragment — top active goals (Core Tier).

Read-only. Concise list aligned with legacy ContextEngine goal block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.agents.token_counter import truncate_to_token_budget
from app.core.runtime import read_ports

_GOAL_LIMIT_DEFAULT = 3
_GOAL_LIMIT_RICH = 5
_STALE_DAYS = 3
_RICH_TAGS = frozenset({"goals", "planning", "review"})


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


def _format_progress(raw: object) -> str:
    if raw is None or raw == "":
        return ""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    pct = int(round(value * 100)) if value <= 1.0 else int(round(value))
    pct = max(0, min(100, pct))
    if pct <= 0:
        return ""
    return f"{pct}%"


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


def format_goal_line(
    row: dict,
    *,
    stagnant_ids: set[str] | None = None,
    rich: bool = False,
    today: date | None = None,
) -> str:
    title = str(row.get("title") or "").strip() or "无标题"
    status = str(row.get("status") or "active").strip() or "active"
    tags = [status]
    goal_id = str(row.get("id") or "")
    if stagnant_ids and goal_id in stagnant_ids:
        tags.append("停滞")

    parts = [f"- [{'|'.join(tags)}] {title}"]

    if rich:
        progress = _format_progress(row.get("progress"))
        if progress:
            parts.append(progress)

    deadline = _format_deadline(row.get("deadline"), today=today)
    if deadline:
        parts.append(deadline)

    return " · ".join(parts) if len(parts) > 1 else parts[0]


@dataclass
class GoalsContextFragment(ContextFragment):
    """Top active goals — Core Tier."""

    id: str = field(default="core.goals", init=False)
    priority: int = field(default=75, init=False)
    max_tokens: int = field(default=600, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"goals", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        rich = bool(ctx.intent_tags & _RICH_TAGS)
        limit = _GOAL_LIMIT_RICH if rich else _GOAL_LIMIT_DEFAULT

        try:
            rows = read_ports.query_top_active_goals(limit=limit)
        except Exception:
            return FragmentResult(content="")

        if not rows:
            return FragmentResult(content="")

        stagnant_ids: set[str] = set()
        try:
            for g in read_ports.query_stagnant_goals(days=_STALE_DAYS, limit=20):
                gid = str(g.get("id") or "")
                if gid:
                    stagnant_ids.add(gid)
        except Exception:
            stagnant_ids = set()

        today = date.today()
        lines = ["## 当前目标\n"]
        lines.extend(
            format_goal_line(row, stagnant_ids=stagnant_ids, rich=rich, today=today)
            for row in rows
        )
        content = truncate_to_token_budget("\n".join(lines), self.max_tokens)

        sources = []
        for row in rows:
            goal_id = str(row.get("id") or "").strip()
            if not goal_id:
                continue
            sources.append({
                "id": goal_id,
                "type": "goal",
                "title": str(row.get("title") or goal_id),
            })

        return FragmentResult(content=content, sources=sources)

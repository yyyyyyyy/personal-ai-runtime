"""GovernanceContextFragment — inject runtime governance state into the prompt.

Shows the LLM a compact view of pending approvals (and, when relevant,
recent tool activity). Stagnant-goal counts are left to core.goals to avoid
duplicate noise. Reads governed projections via read_ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_PENDING_DETAIL_LIMIT = 3


def _format_pending_approvals(rows: list[dict], *, total: int) -> list[str]:
    """Render actionable pending-approval lines."""
    if total <= 0 and not rows:
        return []

    actions: list[str] = []
    seen: set[str] = set()
    for row in rows:
        action = str(row.get("action") or "").strip() or "unknown"
        if action in seen:
            continue
        seen.add(action)
        actions.append(action)
        if len(actions) >= _PENDING_DETAIL_LIMIT:
            break

    count = total if total > 0 else len(rows)
    if not actions:
        return [f"- 待审批操作: {count} 项"]

    shown = ", ".join(actions)
    if count > len(actions):
        return [f"- 待审批: {shown} 等（共 {count} 项）"]
    return [f"- 待审批: {shown}（共 {count} 项）"]


@dataclass
class GovernanceContextFragment(ContextFragment):
    """Render a compact governance snapshot for the LLM.

    Priority 85 places it in the Priority tier (>= 80) so it is loaded on
    every chat turn without requiring a scenario tag match. Also included in
    the post_tool stage set so deferred approvals remain visible after tools.
    """

    id: str = field(default="core.governance", init=False)
    priority: int = field(default=85, init=False)
    max_tokens: int = field(default=400, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"governance", "universal"}),
        init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        lines: list[str] = []
        pending_rows: list[dict] = []
        pending_count = 0

        try:
            pending_rows = read_ports.query_pending_approvals(limit=_PENDING_DETAIL_LIMIT)
            pending_count = read_ports.query_pending_approval_count()
        except Exception:
            pending_rows, pending_count = [], 0

        lines.extend(_format_pending_approvals(pending_rows, total=pending_count))

        # Recent tools: useful after a tool turn, or when something is waiting
        # on approval (explains what triggered the deferral).
        show_tools = (ctx.stage == "post_tool") or pending_count > 0
        if show_tools:
            try:
                recent_tools = read_ports.query_recent_tool_names(limit=3)
            except Exception:
                recent_tools = []
            if recent_tools:
                lines.append(f"- 最近工具活动: {', '.join(recent_tools)}")

        # Stagnant goals are surfaced on core.goals lines — skip the duplicate count.

        if not lines:
            return FragmentResult(content="")
        body = "\n".join(lines)
        return FragmentResult(content=f"## 当前运行时状态\n{body}")

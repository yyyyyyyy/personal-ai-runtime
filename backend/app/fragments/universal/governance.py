"""GovernanceContextFragment — inject runtime governance state into the prompt.

Shows the LLM a compact view of the current runtime state so it can reason
about pending approvals, recent tool activity, and stagnant goals. Activates
the previously-dormant ExecutionContextProvider / CapabilityContextProvider
(FACT-36) by surfacing their snapshots as a Priority-tier fragment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class GovernanceContextFragment(ContextFragment):
    """Render a compact governance snapshot for the LLM.

    Priority 85 places it in the Priority tier (>= 80) so it is loaded on
    every chat turn without requiring a scenario tag match.
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

        pending_count = read_ports.query_pending_approval_count()
        if pending_count > 0:
            lines.append(f"- 待审批操作: {pending_count} 项")

        recent_tools = read_ports.query_recent_tool_names(limit=3)
        if recent_tools:
            tools_str = ", ".join(recent_tools)
            lines.append(f"- 最近工具活动: {tools_str}")

        stagnant = read_ports.query_stagnant_goal_count()
        if stagnant > 0:
            lines.append(f"- 停滞目标: {stagnant} 个需要关注")

        if not lines:
            return FragmentResult(content="")
        body = "\n".join(lines)
        return FragmentResult(content=f"## 当前运行时状态\n{body}")

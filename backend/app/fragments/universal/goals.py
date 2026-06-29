"""GoalsContextFragment — top active goals (Core Tier).

Read-only. Concise list aligned with legacy ContextEngine goal appendix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_GOAL_LIMIT = 5


@dataclass
class GoalsContextFragment(ContextFragment):
    """Surface top active goals for prompt compilation."""

    id: str = field(default="core.goals", init=False)
    priority: int = field(default=75, init=False)
    max_tokens: int = field(default=1000, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"goals", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        rows = read_ports.query_top_active_goals(limit=_GOAL_LIMIT)

        if not rows:
            return FragmentResult(content="")

        lines = ["## Top Active Goals\n"]
        for row in rows:
            title = row.get("title", "")
            status = row.get("status", "")
            deadline = row.get("deadline")
            suffix = f" (deadline: {deadline[:10]})" if deadline else ""
            lines.append(f"- [{status}] {title}{suffix}")
        return FragmentResult(content="\n".join(lines))

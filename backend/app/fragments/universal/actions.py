"""ActionsContextFragment — pending actions from Runtime state.

Read-only. Same query as legacy ContextEngine pending-actions path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_PENDING_ACTION_LIMIT = 5


@dataclass
class ActionsContextFragment(ContextFragment):
    """Surface pending actions for prompt compilation."""

    id: str = field(default="core.actions", init=False)
    priority: int = field(default=70, init=False)
    max_tokens: int = field(default=1000, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"actions", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        pending = read_ports.query_pending_actions(limit=_PENDING_ACTION_LIMIT)
        if not pending:
            return FragmentResult(content="")

        lines = ["## Pending Actions\n"]
        for action in pending[:_PENDING_ACTION_LIMIT]:
            status = action.get("status", "pending")
            title = action.get("title", "")
            lines.append(f"- [{status}] {title}")
        return FragmentResult(content="\n".join(lines))

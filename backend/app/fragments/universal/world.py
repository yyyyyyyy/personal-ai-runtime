"""WorldContextFragment — 30-day life snapshot (Scenario: planning / review).

Read-only. Wraps world_model.to_prompt_context(); does not embed world_model in Compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class WorldContextFragment(ContextFragment):
    """Surface world snapshot when planning or review intent is detected."""

    id: str = field(default="core.world", init=False)
    priority: int = field(default=55, init=False)
    max_tokens: int = field(default=1000, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"world", "planning", "review"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        content = read_ports.query_world_context()
        if not content or not content.strip():
            return FragmentResult(content="")
        return FragmentResult(content=content)

"""BackgroundContextFragment — 语义记忆 + 30天生活快照。

读 read_ports 的通用背景上下文层。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class BackgroundContextFragment(ContextFragment):
    """Semantic memory recall + world snapshot — universal background context."""

    id: str = field(default="core.background", init=False)
    priority: int = field(default=58, init=False)  # between memory(60) and world(55)
    max_tokens: int = field(default=3000, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"memory", "world", "planning", "review", "universal"}),
        init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        parts: list[str] = []
        sources: list[dict] = []

        # Unified recall: memories + knowledge documents in one pass.
        # This lets a single chat answer cite both personal memories and
        # uploaded documents, instead of only memories (previously knowledge
        # was only injected via the scenario-tier KnowledgeContextFragment).
        if ctx.user_message:
            ctx_str, ctx_sources = read_ports.retrieve_unified_with_sources(ctx.user_message)
            if ctx_str:
                parts.append(ctx_str)
                sources.extend(ctx_sources)

        # World snapshot
        world = read_ports.query_world_context()
        if world and world.strip():
            parts.append(world)

        if not parts:
            return FragmentResult(content="")
        return FragmentResult(content="\n\n".join(parts), sources=sources)

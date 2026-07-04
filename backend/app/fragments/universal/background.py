"""BackgroundContextFragment — 语义记忆 + 30天生活快照（合并 memory + world）。

v0.7.0: MemoryContextFragment + WorldContextFragment 合并。两者都是
read_ports 的瘦封装，同属于 universal 背景上下文层。
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

        # Memory recall
        if ctx.user_message:
            mem, mem_sources = read_ports.retrieve_memory_with_sources(ctx.user_message)
            if mem:
                parts.append(mem)
                sources.extend(mem_sources)

        # World snapshot
        world = read_ports.query_world_context()
        if world and world.strip():
            parts.append(world)

        if not parts:
            return FragmentResult(content="")
        return FragmentResult(content="\n\n".join(parts), sources=sources)

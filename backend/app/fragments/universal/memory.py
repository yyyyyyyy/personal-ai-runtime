"""MemoryContextFragment — 语义记忆检索。

只读 MemoryEngine.search_memory。不写 Memory，不发 Event。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class MemoryContextFragment(ContextFragment):
    """检索与当前对话相关的长期记忆。"""

    id: str = field(default="core.memory", init=False)
    priority: int = field(default=60, init=False)
    max_tokens: int = field(default=2000, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"memory", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        if not ctx.user_message:
            return FragmentResult(content="")

        context_str, sources = read_ports.retrieve_memory_with_sources(ctx.user_message)
        return FragmentResult(content=context_str, sources=sources)

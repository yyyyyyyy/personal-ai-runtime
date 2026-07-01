"""Context Runtime — the core primitives of the Context Operating System.

    Fragment  = 提供事实
    Tool      = 执行动作（MCP Hub 全局资产）

Fragment 是 Runtime 的一级认知原语。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── RuntimeContext ────────────────────────────────────────────────────────

@dataclass
class RuntimeContext:
    """传递给所有 Fragment 的运行时上下文。

    仅包含最小必要信息。不持有 Kernel 引用（Fragment 不能直接写真相层）。
    """
    user_message: str = ""
    conversation_id: str = ""
    execution_id: str = ""


# ── FragmentResult ───────────────────────────────────────────────────────

@dataclass
class FragmentResult:
    """Fragment.collect() 的返回值。"""
    content: str = ""
    token_count: int = 0
    sources: list[dict] = field(default_factory=list)
    # Each source: {"id": str, "type": "memory"|"knowledge"|"email"|"goal", "title": str}

    def __post_init__(self):
        if self.token_count == 0 and self.content:
            self.token_count = max(1, len(self.content) // 4)


# ── ContextFragment ──────────────────────────────────────────────────────

@dataclass
class ContextFragment:
    """最小认知单元 — Fragment 是 Runtime 的一级概念。

    Fragment ≠ Data Source。Fragment = Cognitive Unit。
    回答的是"模型此刻需要知道什么"，不是"这张表需要被读取"。

    负责：数据获取、数据过滤、数据转换、上下文构建。
    不负责：推理、决策、任务编排、UI 呈现。

    统一接口：collect(ctx) → FragmentResult
    """

    id: str = ""

    # Fragment 元数据 — 供 Assembler 做选择和裁剪
    priority: int = 50          # 0-100，越高越优先加载
    max_tokens: int = 2000      # 单个 Fragment 的 token 上限
    tags: frozenset[str] = field(default_factory=frozenset)
    # abstract capabilities required for this fragment.
    # Empty set means "always available". Governance Policy uses this
    # to suppress fragments when required capabilities are unavailable.
    required_capabilities: frozenset[str] = field(default_factory=frozenset)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        """收集并返回认知上下文。"""
        return FragmentResult(content="")


# ── Fragment Registry ────────────────────────────────────────────────────

class FragmentRegistry:
    """Context Fragment 注册表 — 纯数据管理，不做策略。"""

    def __init__(self):
        self._fragments: dict[str, ContextFragment] = {}

    def register(self, fragment: ContextFragment) -> None:
        self._fragments[fragment.id] = fragment

    def get(self, fragment_id: str) -> ContextFragment | None:
        return self._fragments.get(fragment_id)

    def list_all(self) -> list[ContextFragment]:
        return list(self._fragments.values())

    def list_ids(self) -> list[str]:
        return sorted(self._fragments.keys())

    def by_tag(self, tag: str) -> list[ContextFragment]:
        """按标签查找所有匹配的 Fragment。"""
        return [f for f in self._fragments.values() if tag in f.tags]

    def by_tags(self, tags: set[str]) -> list[ContextFragment]:
        """按多个标签查找（任意匹配）。"""
        return [f for f in self._fragments.values() if tags & f.tags]


# ── Global singleton ────────────────────────────────────────────────────

fragment_registry = FragmentRegistry()

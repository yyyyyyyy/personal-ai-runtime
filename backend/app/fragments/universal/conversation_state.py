"""ConversationStateFragment — 当前会话状态摘要。

不返回原始 transcript。返回的是模型可用的认知上下文：
  - 当前讨论主题
  - 最近达成结论
  - 当前待解决问题
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class ConversationStateFragment(ContextFragment):
    """当前会话认知状态 — 摘要而非原始 transcript。"""

    id: str = field(default="core.conversation_state", init=False)
    priority: int = field(default=90, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"conversation", "universal"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        if not ctx.conversation_id:
            return FragmentResult(content="（新会话）")

        rows = read_ports.query_conversation_messages(ctx.conversation_id, limit=20)

        if not rows:
            return FragmentResult(content="（空会话）")

        # 返回最近消息的认知摘要，而非原始 transcript
        reversed_rows = list(reversed(rows))
        lines = ["## 当前会话状态\n"]

        # 提取最近几轮对话作为摘要
        recent = reversed_rows[-6:] if len(reversed_rows) > 6 else reversed_rows
        for r in recent:
            role_label = "用户" if r.get("role") == "user" else "AI"
            content = (r.get("content") or "")[:200]  # 截断，避免过长
            lines.append(f"- [{role_label}] {content}")

        return FragmentResult(content="\n".join(lines))

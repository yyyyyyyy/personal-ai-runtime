"""ConversationStateFragment — 当前会话认知状态摘要。

不返回原始 transcript（完整历史由 Brain 注入）。返回：
  - 当前讨论主题
  - 最近结论/回复要点
  - 当前待解决问题
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.agents.token_counter import truncate_to_token_budget
from app.core.runtime import read_ports

_QUESTION_TAIL = re.compile(
    r"(吗|呢|怎么|如何|什么|为何|为什么|哪|是否|能否|可以吗|好吗|行吗)[\s\W]*$",
)
_QUESTION_HEAD = re.compile(r"^(怎么|如何|什么|为什么|为何|哪|是否|能否)")


def _one_line(text: str, max_len: int = 100) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _strip_content(text: str) -> str:
    try:
        from app.core.agents.tool_markup import strip_tool_markup

        return strip_tool_markup(text or "") or ""
    except Exception:
        return text or ""


def _looks_like_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "?" in t or "？" in t:
        return True
    return bool(_QUESTION_TAIL.search(t) or _QUESTION_HEAD.search(t))


def build_conversation_state_summary(
    rows: list[dict],
    *,
    user_message: str = "",
    stage: str = "chat",
) -> str:
    """Build a cognitive summary from recent messages (chronological)."""
    users = [r for r in rows if r.get("role") == "user"]
    assistants = [r for r in rows if r.get("role") == "assistant"]
    tools = [r for r in rows if r.get("role") == "tool"]

    lines = ["## 当前会话状态"]

    topic_src = (user_message or "").strip()
    if not topic_src and users:
        topic_src = str(users[-1].get("content") or "")
    topic = _one_line(_strip_content(topic_src), 120)
    if topic:
        lines.append(f"- 当前主题: {topic}")

    open_qs: list[str] = []
    seen: set[str] = set()
    for u in users[-4:]:
        raw = _strip_content(str(u.get("content") or ""))
        if not _looks_like_question(raw):
            continue
        q = _one_line(raw, 80)
        if not q or q in seen:
            continue
        if topic and q.rstrip("…") == topic.rstrip("…"):
            continue
        seen.add(q)
        open_qs.append(q)
    if open_qs:
        lines.append("- 待解决问题:")
        for q in open_qs[-2:]:
            lines.append(f"  - {q}")

    if assistants:
        conclusion = _one_line(_strip_content(str(assistants[-1].get("content") or "")), 140)
        if conclusion:
            lines.append(f"- 最近结论/回复要点: {conclusion}")

    if stage == "post_tool" and tools:
        tool_preview = _one_line(_strip_content(str(tools[-1].get("content") or "")), 80)
        if tool_preview:
            lines.append(f"- 最近工具结果: {tool_preview}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


@dataclass
class ConversationStateFragment(ContextFragment):
    """当前会话认知状态 — 摘要而非原始 transcript。"""

    id: str = field(default="core.conversation_state", init=False)
    priority: int = field(default=80, init=False)
    max_tokens: int = field(default=500, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"conversation", "universal"}),
        init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        if not ctx.conversation_id:
            return FragmentResult(content="")

        try:
            rows = read_ports.query_conversation_messages(
                ctx.conversation_id,
                limit=12,
                order="created_at_desc",
            )
        except Exception:
            return FragmentResult(content="")

        if not rows:
            return FragmentResult(content="")

        chronological = list(reversed(rows))
        summary = build_conversation_state_summary(
            chronological,
            user_message=ctx.user_message or "",
            stage=ctx.stage or "chat",
        )
        if not summary:
            return FragmentResult(content="")

        return FragmentResult(
            content=truncate_to_token_budget(summary, self.max_tokens),
        )

"""BackgroundContextFragment — 语义记忆 + 近30天生活快照。

读 read_ports 的通用背景上下文层。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.agents.token_counter import count_text_tokens, truncate_to_token_budget
from app.core.runtime import read_ports

_TRIVIAL_MESSAGES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "ok",
        "okay",
        "thanks",
        "thank you",
        "thx",
        "你好",
        "您好",
        "嗨",
        "在吗",
        "谢谢",
        "好的",
        "嗯",
        "哦",
    }
)

_WORLD_TOKEN_RESERVE = 180


def _normalize_trivial(message: str) -> str:
    text = (message or "").strip().lower()
    text = re.sub(r"[!?。！？~～.…\s]+", "", text)
    return text


def should_recall_background(message: str) -> bool:
    """Skip vector recall for empty / greeting / ultra-short chatter."""
    text = (message or "").strip()
    if len(text) < 4:
        return False
    if _normalize_trivial(text) in _TRIVIAL_MESSAGES:
        return False
    if len(text) < 8 and not re.search(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{4,}", text):
        return False
    return True


@dataclass
class BackgroundContextFragment(ContextFragment):
    """Semantic memory recall + world snapshot — universal background context."""

    id: str = field(default="core.background", init=False)
    priority: int = field(default=58, init=False)
    max_tokens: int = field(default=3000, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"memory", "world", "planning", "review", "universal"}),
        init=False,
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        parts: list[str] = []
        sources: list[dict] = []

        if should_recall_background(ctx.user_message):
            max_knowledge = 0 if "knowledge" in ctx.intent_tags else 3
            try:
                ctx_str, ctx_sources = read_ports.retrieve_unified_with_sources(
                    ctx.user_message,
                    max_knowledge=max_knowledge,
                )
                if ctx_str:
                    parts.append(ctx_str)
                    sources.extend(ctx_sources)
            except Exception:
                pass

        try:
            world = read_ports.query_world_context()
            if world and world.strip():
                parts.append(world.strip())
        except Exception:
            pass

        if not parts:
            return FragmentResult(content="")

        if len(parts) >= 2:
            world_part = parts[-1]
            recall_part = "\n\n".join(parts[:-1])
            world_tokens = count_text_tokens(world_part)
            recall_budget = max(0, self.max_tokens - max(world_tokens, _WORLD_TOKEN_RESERVE))
            recall_part = truncate_to_token_budget(recall_part, recall_budget)
            content = "\n\n".join(p for p in (recall_part, world_part) if p)
        else:
            content = truncate_to_token_budget(parts[0], self.max_tokens)

        return FragmentResult(content=content, sources=sources)

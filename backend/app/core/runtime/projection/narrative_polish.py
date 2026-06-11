"""LLM polish path for Identity Projection narratives — IDENTITY_NARRATIVE_PROMPT."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.core.agents.llm_router import llm_router
from app.core.runtime.egress.egress_gate import prepare_llm_egress
from app.core.runtime.projection.identity_lint import lint_identity_hard_failures
from app.core.runtime.projection.narrative_audit import build_narrative_audit

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你正在生成 Identity Projection 草稿（非身份认定）。

规则：
1. 开篇保留「系统投影草稿」免责声明。
2. 轨迹：列举所有 active 竞争对；标注 identity_narrative_opt_in 状态；禁止只写一条线。
3. Claim/Belief：仅用「系统推测」「可能」「模式假设」；proposed 不得写作定论。
4. 禁止 Outcome Backfill：不得写「事实证明你当年是对的」。
5. 结尾：提醒用户可在「记忆」「轨迹」页署名或争议。

在保留结构与事实的前提下润色下文，不得删除轨迹视角段落。"""


async def _polish_async(template: str) -> str:
    client, provider = llm_router.get_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": template},
    ]
    messages, _audit = prepare_llm_egress(messages, purpose="review_narrative")
    response = await client.chat.completions.create(
        model=provider.model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.4,
        max_tokens=settings.llm_max_tokens,
    )
    return (response.choices[0].message.content or "").strip() or template


def polish_narrative(
    template: str,
    *,
    trajectories: list[dict[str, Any]],
    memories: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    trajectory_link_seqs: dict[str, list[int]] | None = None,
    released_trajectory_ids: set[str] | None = None,
) -> str:
    """Polish review narrative via LLM; fall back to template on lint failure or error."""
    return asyncio.run(
        polish_narrative_async(
            template,
            trajectories=trajectories,
            memories=memories,
            events=events,
            trajectory_link_seqs=trajectory_link_seqs,
            released_trajectory_ids=released_trajectory_ids,
        )
    )


async def polish_narrative_async(
    template: str,
    *,
    trajectories: list[dict[str, Any]],
    memories: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    trajectory_link_seqs: dict[str, list[int]] | None = None,
    released_trajectory_ids: set[str] | None = None,
) -> str:
    """Async variant of polish_narrative for use within async callers."""
    if not settings.review_narrative_llm_enabled or not template.strip():
        return template

    try:
        polished = await _polish_async(template)
    except Exception as exc:
        logger.warning("narrative polish LLM failed: %s", exc)
        return template

    if not polished.strip():
        return template

    audit = build_narrative_audit(
        polished,
        trajectories,
        memories=memories or [],
        events=events or [],
        trajectory_link_seqs=trajectory_link_seqs or {},
    )
    failures = lint_identity_hard_failures(
        polished,
        trajectories=trajectories,
        narrative_meta=audit,
        released_trajectory_ids=released_trajectory_ids,
    )
    if failures:
        logger.warning("narrative polish lint failed, using template: %s", failures[:3])
        return template

    return polished

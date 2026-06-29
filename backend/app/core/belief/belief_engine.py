"""Belief Engine — Projection-Driven Reflection.

Pattern → Reflection → Belief

Key constraint:
    Reflection consumes PROJECTIONS only (patterns, goals, memories).
    It NEVER reads raw events. This enforces the separation:
        Runtime = computation (Pattern Aggregator)
        Belief  = interpretation (this module)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReflectionContext:
    """Input to Reflection — projections only, never raw events."""
    patterns: list[dict] = field(default_factory=list)
    goals: list[dict] = field(default_factory=list)
    memories: list[dict] = field(default_factory=list)


def _format_patterns(patterns: list[dict]) -> str:
    """Render patterns as structured text for LLM prompt."""
    if not patterns:
        return "无模式数据"

    grouped: dict[str, list[dict]] = {}
    for p in patterns:
        grouped.setdefault(p["pattern_type"], []).append(p)

    lines = []
    for ptype, items in grouped.items():
        type_label = {
            "time_distribution": "时间分布",
            "topic_distribution": "主题分布",
            "trend": "趋势",
        }.get(ptype, ptype)
        lines.append(f"\n## {type_label}")
        for item in items[:5]:  # top 5 per type
            try:
                stats = json.loads(item["statistics"])
            except (json.JSONDecodeError, TypeError):
                stats = {}
            metric = item.get("metric", "")
            window = item.get("window_days", "")
            lines.append(f"- {metric} ({window}天窗口): {json.dumps(stats, ensure_ascii=False)}")
    return "\n".join(lines) if lines else "无模式数据"


def _format_goals(goals: list[dict]) -> str:
    if not goals:
        return "无活跃目标"
    lines = []
    for g in goals[:5]:
        title = g.get("title", "")
        status = g.get("status", "")
        progress = g.get("progress", 0)
        importance = g.get("importance", 0)
        urgency = g.get("urgency", 0)
        deadline = g.get("deadline", "")
        line = f"- [{status}] {title} (进度:{progress} 重要性:{importance} 紧迫性:{urgency}"
        if deadline:
            line += f" 截止:{deadline}"
        line += ")"
        lines.append(line)
    return "\n".join(lines)


def _format_memories(memories: list[dict]) -> str:
    if not memories:
        return "无历史认知"
    lines = []
    for m in memories[:5]:
        content = m.get("content", "")
        confidence = m.get("confidence", 0)
        belief_type = m.get("belief_type", "observation")
        lines.append(f"- [{belief_type}] {content} (置信度:{confidence:.2f})")
    return "\n".join(lines)


REFLECTION_SYSTEM_PROMPT = """你是一个个人认知助手。你的任务是分析统计数据、目标进展和历史认知，生成洞察和信念。

重要约束：
1. 你只能基于下面提供的 Pattern（模式）、Goal（目标）和 Memory（历史认知）进行分析
2. 不要编造数据中不存在的事实
3. 每条信念必须基于至少一个 Pattern 的数据
4. 如果数据不足以形成信念，如实说"数据不足"

输出格式（严格 JSON）：
{
    "beliefs": [
        {
            "content": "信念内容（一句话，用中文）",
            "confidence": 0.0-1.0,
            "derived_from_patterns": ["pat_xxx", ...],
            "category": "insight"
        }
    ]
}"""


class BeliefEngine:
    """Reflection engine — turns projections into beliefs.

    Input: ReflectionContext (patterns, goals, memories)
    Output: BeliefFormed events via kernel.emit_event
    """

    async def reflect(self, ctx: ReflectionContext) -> list[dict]:
        """Run the Belief Reflection pipeline.

        Returns: list of belief dicts that were emitted.
        """
        # 1. Build the prompt
        prompt = self._build_prompt(ctx)

        # 2. Call LLM
        response = await self._call_llm(prompt)

        # 3. Parse structured beliefs
        beliefs = self._parse_response(response)

        # 4. Emit BeliefFormed events
        emitted = []
        for belief in beliefs:
            evidence_chain = belief.get("derived_from_patterns", [])
            belief_id = f"blf_{uuid.uuid4().hex}"

            from app.core.runtime.kernel_instance import kernel

            kernel.emit_event(
                type="BeliefFormed",
                aggregate_type="memory",
                aggregate_id=belief_id,
                payload={
                    "category": belief.get("category", "insight"),
                    "content": belief["content"],
                    "confidence": belief.get("confidence", 0.5),
                    "belief_type": "belief",
                    "source": "reflection",
                    "derived_from_event": json.dumps({
                        "patterns": evidence_chain,
                    }),
                    "evidence_chain": json.dumps({
                        "patterns": evidence_chain,
                    }),
                },
                actor="kernel",
            )
            emitted.append({
                "id": belief_id,
                "content": belief["content"],
                "confidence": belief.get("confidence", 0.5),
                "evidence_chain": evidence_chain,
            })

        logger.info("BeliefEngine produced %d beliefs", len(emitted))
        return emitted

    def _build_prompt(self, ctx: ReflectionContext) -> str:
        return (
            "请根据以下数据生成认知信念：\n\n"
            "## 模式 (Patterns)\n"
            f"{_format_patterns(ctx.patterns)}\n\n"
            "## 目标 (Goals)\n"
            f"{_format_goals(ctx.goals)}\n\n"
            "## 历史认知 (Memories)\n"
            f"{_format_memories(ctx.memories)}\n\n"
            "请以 JSON 格式输出。"
        )

    async def _call_llm(self, user_prompt: str) -> str:
        """Call the LLM for reflection. Uses the same router as Brain."""
        from app.config import settings
        from app.core.agents.llm_router import llm_router

        client, provider = llm_router.get_client()

        try:
            response = await client.chat.completions.create(  # type: ignore[call-overload]
                model=provider.model,
                messages=[
                    {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # lower temperature for structured output
                max_tokens=settings.llm_max_tokens,
            )
            return response.choices[0].message.content or "{}"
        except Exception as e:
            logger.error("BeliefEngine LLM call failed: %s", e)
            return "{}"

    def _parse_response(self, response: str) -> list[dict]:
        """Extract beliefs array from LLM JSON response."""
        try:
            # Try direct JSON parse
            data = json.loads(response)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "beliefs" in data:
                return data["beliefs"]
            return []
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        import re
        match = re.search(r"\{[\s\S]*\}", response)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and "beliefs" in data:
                    beliefs = data["beliefs"]
                    if isinstance(beliefs, list):
                        return beliefs
            except json.JSONDecodeError:
                pass

        logger.warning("BeliefEngine: could not parse LLM response: %s", response[:200])
        return []


belief_engine = BeliefEngine()

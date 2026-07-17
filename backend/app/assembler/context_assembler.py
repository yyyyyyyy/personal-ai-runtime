"""Context Assembler — 收集 Fragment、按 priority 排序、在 budget 内组装。

流程：
  1. 并行 collect() 所有 Fragment（asyncio.gather）
  2. 按 priority 降序排序
  3. 在 budget 内组装
  4. join 为最终 system prompt
  5. 收集所有 sources 供引用溯源
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.context_runtime import (
    ContextFragment,
    FragmentResult,
    RuntimeContext,
)
from app.core.agents.token_counter import count_text_tokens


@dataclass
class AssemblyResult:
    """组装结果：包含 system prompt 和引用的 sources。"""
    system_prompt: str = ""
    sources: list[dict] = field(default_factory=list)


class ContextAssembler:
    """组装 Context Fragment 为最终 system prompt。

    策略：
    - 按 Fragment.priority 降序加载
    - 超过 budget 时跳过低优先级 Fragment
    - Empty fragments are skipped
    """

    async def assemble(
        self,
        fragments: list[ContextFragment],
        ctx: RuntimeContext,
        budget: int = 32000,
    ) -> str:
        """收集并组装 Fragment（向后兼容，只返回 prompt）。"""
        result = await self.assemble_with_sources(fragments, ctx, budget)
        return result.system_prompt

    async def assemble_with_sources(
        self,
        fragments: list[ContextFragment],
        ctx: RuntimeContext,
        budget: int = 32000,
    ) -> AssemblyResult:
        """收集并组装 Fragment，同时返回引用的 sources。"""
        if not fragments:
            return AssemblyResult()

        # 1. 并行 collect() 所有 Fragment
        collected = await asyncio.gather(
            *(f.collect(ctx) for f in fragments),
            return_exceptions=True,
        )
        results: list[tuple[ContextFragment, FragmentResult]] = []
        for i, result in enumerate(collected):
            if isinstance(result, BaseException):
                continue  # skip fragments that raised
            results.append((fragments[i], result))

        # 2. 按 priority 降序排序
        results.sort(key=lambda x: x[0].priority, reverse=True)

        # 3. 在 budget 内组装
        parts: list[str] = []
        all_sources: list[dict] = []
        used = 0

        for frag, result in results:
            content = result.content or ""
            if not content and frag.priority < 100:
                continue

            # Respect per-fragment max_tokens when set (>0).
            max_tok = getattr(frag, "max_tokens", 0) or 0
            if content and max_tok > 0 and count_text_tokens(content) > max_tok:
                # Soft trim by characters; fragments should self-limit, this is a backstop.
                approx_chars = max(16, max_tok * 4)
                content = content[:approx_chars].rstrip() + "…"
                result = FragmentResult(content=content, sources=result.sources)

            token_count = count_text_tokens(content) if content else 0

            # Identity Fragment 永不被丢弃（priority=100）
            if frag.priority >= 100:
                parts.append(content)
                used += token_count
                all_sources.extend(result.sources)
                continue

            if not content:
                continue

            # 预算不足时跳过
            if used + token_count > budget:
                continue

            parts.append(content)
            used += token_count
            all_sources.extend(result.sources)

        system_prompt = "\n\n---\n".join(parts) if parts else ""
        return AssemblyResult(system_prompt=system_prompt, sources=all_sources)

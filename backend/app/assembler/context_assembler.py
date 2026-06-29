"""Context Assembler — 收集 Fragment、按 priority 排序、在 budget 内组装。

流程：
  1. collect() 所有 Fragment
  2. 按 priority 降序排序
  3. 在 budget 内组装
  4. join 为最终 system prompt
  5. 收集所有 sources 供引用溯源
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import (
    ContextFragment,
    FragmentResult,
    RuntimeContext,
    estimate_tokens,
)


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

        # 1. 并发 collect() 所有 Fragment
        results: list[tuple[ContextFragment, FragmentResult]] = []
        for f in fragments:
            result = await f.collect(ctx)
            results.append((f, result))

        # 2. 按 priority 降序排序
        results.sort(key=lambda x: x[0].priority, reverse=True)

        # 3. 在 budget 内组装
        parts: list[str] = []
        all_sources: list[dict] = []
        used = 0

        for frag, result in results:
            token_count = estimate_tokens(result.content) if result.content else 0

            # Identity Fragment 永不被丢弃（priority=100）
            if frag.priority >= 100:
                parts.append(result.content)
                used += token_count
                all_sources.extend(result.sources)
                continue

            if not result.content:
                continue

            # 预算不足时跳过
            if used + token_count > budget:
                continue

            parts.append(result.content)
            used += token_count
            all_sources.extend(result.sources)

        system_prompt = "\n\n---\n".join(parts) if parts else ""
        return AssemblyResult(system_prompt=system_prompt, sources=all_sources)

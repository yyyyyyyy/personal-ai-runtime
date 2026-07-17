"""Fragment Selector — 根据 AnalysisResult 选择需要加载的 Fragment。

策略分层：
  1. Core Tier — Runtime 认知原语，始终加载
  2. Priority Tier — priority >= 80 的 Universal Fragment
  3. Scenario Tier — 意图标签映射的 Scenario Fragment
"""

from __future__ import annotations

from app.context_runtime import ContextFragment, FragmentRegistry, fragment_registry
from app.core.runtime.governance.query_analyzer import AnalysisResult

# ── Core Tier — Runtime cognition primitives (always selected) ───────────

CORE_TIER_FRAGMENT_IDS: tuple[str, ...] = (
    "core.background",
    "core.timeline",
    "core.goals",
)

# Stage-specific fragment sets (Policy Activation)

POST_TOOL_FRAGMENT_IDS: tuple[str, ...] = (
    "core.background",
    "core.conversation_state",
    "core.governance",  # pending approvals after tool deferral
)

BRIEF_FRAGMENT_IDS: tuple[str, ...] = (
    "core.goals",
    "core.background",
    "calendar.today",
    "calendar.upcoming",
)

_PRIORITY_TIER_MIN = 80

# ── 标签 → Fragment ID 映射 ────────────────────────────────────────────────

_SCENARIO_TAG_FRAGMENTS: dict[str, list[str]] = {
    "mail":      ["mail.recent_emails", "mail.email_search"],
    "calendar":  ["calendar.today", "calendar.upcoming"],
    "planning":  ["core.background"],
    "review":    ["core.background"],
    "knowledge": ["scenario.knowledge"],
}


class FragmentSelector:
    """根据分析结果选择 Fragment。"""

    def __init__(self, registry: FragmentRegistry | None = None):
        self._registry = registry or fragment_registry

    def select(self, analysis: AnalysisResult) -> list[ContextFragment]:
        """Chat stage — full Core + Priority + Scenario tiers."""
        return self._select_chat(analysis)

    def select_for_stage(
        self,
        analysis: AnalysisResult,
        stage: str,
    ) -> list[ContextFragment]:
        if stage == "post_tool":
            return self._select_post_tool(analysis)
        if stage == "brief":
            return self._select_brief(analysis)
        return self._select_chat(analysis)

    def _select_chat(self, analysis: AnalysisResult) -> list[ContextFragment]:
        selected: list[ContextFragment] = []
        seen: set[str] = set()

        # 1. Core Tier — always load runtime cognition primitives
        for fid in CORE_TIER_FRAGMENT_IDS:
            frag = self._registry.get(fid)
            if frag is not None and fid not in seen:
                selected.append(frag)
                seen.add(fid)

        # 2. Priority Tier — high-priority universal fragments (e.g. conversation_state)
        for f in self._registry.list_all():
            if f.priority >= _PRIORITY_TIER_MIN and f.id not in seen:
                selected.append(f)
                seen.add(f.id)

        # 3. Scenario Tier — intent tag mapping
        self._append_scenario(selected, seen, analysis)
        return selected

    def _select_post_tool(self, analysis: AnalysisResult) -> list[ContextFragment]:
        """Reduced context after tool execution — memory, conversation, scenario only."""
        selected: list[ContextFragment] = []
        seen: set[str] = set()

        for fid in POST_TOOL_FRAGMENT_IDS:
            frag = self._registry.get(fid)
            if frag is not None and fid not in seen:
                selected.append(frag)
                seen.add(fid)

        self._append_scenario(selected, seen, analysis)
        return selected

    def _select_brief(self, analysis: AnalysisResult) -> list[ContextFragment]:
        """Summary-oriented context — goals, world, calendar."""
        selected: list[ContextFragment] = []
        seen: set[str] = set()

        for fid in BRIEF_FRAGMENT_IDS:
            frag = self._registry.get(fid)
            if frag is not None and fid not in seen:
                selected.append(frag)
                seen.add(fid)

        return selected

    def _append_scenario(
        self,
        selected: list[ContextFragment],
        seen: set[str],
        analysis: AnalysisResult,
    ) -> None:
        for tag in analysis.tags:
            fragment_ids = _SCENARIO_TAG_FRAGMENTS.get(tag, [])
            for fid in fragment_ids:
                if fid in seen:
                    continue
                frag = self._registry.get(fid)
                if frag is not None:
                    selected.append(frag)
                    seen.add(fid)


def reachable_fragment_ids(
    registry: FragmentRegistry,
    *,
    tags: set[str] | None = None,
) -> set[str]:
    """Return fragment IDs selected for the given tags (empty = default chat)."""
    selector = FragmentSelector(registry)
    selected = selector.select(AnalysisResult(tags=tags or set()))
    return {f.id for f in selected}

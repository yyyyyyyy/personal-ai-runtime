"""Phase 5 — fragment registry audit and reachability tests."""

from __future__ import annotations

import pytest

from app.context_runtime import FragmentRegistry
from app.core.runtime.governance.fragment_selector import (
    _SCENARIO_TAG_FRAGMENTS,
    CORE_TIER_FRAGMENT_IDS,
    reachable_fragment_ids,
)
from app.fragments.register import register_all_fragments

_EXPECTED_FRAGMENT_COUNT = 10  # v0.7.0: memory+world merged into background, mail+calendar identity merged into existing fragments

FRAGMENT_TRIGGER_MATRIX: dict[str, str] = {
    "core.background": "Core Tier",
    "core.timeline": "Core Tier",  # merged actions + events
    "core.goals": "Core Tier",
    "core.governance": "Priority Tier (>=80)",  # runtime governance snapshot
    "core.conversation_state": "Priority Tier (>=80)",
    "mail.recent_emails": "Scenario: mail tag",
    "mail.email_search": "Scenario: mail tag",
    "calendar.today": "Scenario: calendar tag",
    "calendar.upcoming": "Scenario: calendar tag",
    "scenario.knowledge": "Scenario: knowledge tag",
}


class TestFragmentRegistryAudit:
    def test_registered_fragment_count(self):
        registry = FragmentRegistry()
        ids = register_all_fragments(registry)
        assert len(ids) == _EXPECTED_FRAGMENT_COUNT

    def test_all_registered_fragments_reachable(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        registered = set(registry.list_ids())

        all_tags = set(_SCENARIO_TAG_FRAGMENTS.keys())
        reachable: set[str] = set()
        reachable |= reachable_fragment_ids(registry, tags=set())
        for tag in all_tags:
            reachable |= reachable_fragment_ids(registry, tags={tag})
        reachable |= reachable_fragment_ids(registry, tags=all_tags)

        unreachable = registered - reachable
        assert unreachable == set(), f"Unreachable fragments: {unreachable}"

    def test_matrix_covers_all_registered(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        registered = set(registry.list_ids())
        assert set(FRAGMENT_TRIGGER_MATRIX.keys()) == registered

    def test_runtime_identity_not_registered(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        assert "runtime.identity" not in registry.list_ids()

    def test_core_goals_always_selected(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        ids = reachable_fragment_ids(registry)
        assert "core.goals" in ids
        assert "core.goals" in CORE_TIER_FRAGMENT_IDS



class TestBackgroundReachability:
    def test_planning_tag_selects_core_background(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        ids = reachable_fragment_ids(registry, tags={"planning"})
        assert "core.background" in ids

    def test_review_tag_selects_core_background(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        ids = reachable_fragment_ids(registry, tags={"review"})
        assert "core.background" in ids

    def test_default_chat_includes_background(self):
        """Default chat includes background (Core Tier — universal context)."""
        registry = FragmentRegistry()
        register_all_fragments(registry)
        ids = reachable_fragment_ids(registry)
        assert "core.background" in ids  # v0.7.0: background is Core Tier


class TestIdentitySingleSource:
    @pytest.mark.asyncio
    async def test_compiler_identity_not_duplicated_in_context(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: ("", []),
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="hello",
                stage="chat",
            ),
        )
        assert result.count("Personal AI Runtime") == 1

"""Tests for Core Tier fragments and selector policy."""

from __future__ import annotations

import pytest


class TestCoreTierSelector:
    """Core Tier fragments are always selected."""

    def test_core_tier_always_selected(self):
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import AnalysisResult
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)
        selector = FragmentSelector(registry)

        selected = selector.select(AnalysisResult(tags=set()))
        ids = {f.id for f in selected}

        assert "core.background" in ids
        assert "core.timeline" in ids
        assert "core.timeline" in ids
        assert "core.goals" in ids
        assert "core.conversation_state" in ids
        assert "runtime.identity" not in ids

    def test_core_tier_no_duplicates_with_priority_tier(self):
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import AnalysisResult
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)
        selector = FragmentSelector(registry)

        selected = selector.select(AnalysisResult(tags={"mail"}))
        ids = [f.id for f in selected]
        assert len(ids) == len(set(ids))


class TestCoreTierRegistration:
    def test_actions_and_events_registered(self):
        from app.context_runtime import FragmentRegistry
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        ids = register_all_fragments(registry)
        assert "core.timeline" in ids
        assert "core.timeline" in ids
        assert "core.background" in ids


class TestCoreTierCompile:
    """PromptCompiler output includes core tier sources when they return content."""

    @pytest.mark.asyncio
    async def test_prompt_compiler_includes_core_tier_content(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        # Patch read_ports.retrieve_unified_with_sources for citation-aware BackgroundContextFragment
        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: ("## Relevant Memories\n- recalled fact", [{"id": "mem1", "type": "memory", "title": "recalled fact"}]),
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [{"status": "pending", "title": "Finish report"}],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [
                {"summary": "Action created: Finish report", "timestamp": "2026-06-18T10:00:00"},
            ],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="conv_1",
                execution_id="exec_1",
                user_message="what did I decide about the project roadmap",
                stage="chat",
            ),
        )

        assert "Personal AI Runtime" in result
        assert "recalled fact" in result
        assert "## 待办动作" in result
        assert "Finish report" in result
        assert "## 近期事件" in result
        assert "Action created: Finish report" in result

    @pytest.mark.asyncio
    async def test_memory_collect_called_on_compile(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        calls: list[str] = []

        def _retrieve_with_sources(msg: str, **kwargs) -> tuple[str, list[dict]]:
            calls.append(msg)
            return "## Relevant Memories\n- item", [{"id": "mem1", "type": "memory", "title": "item"}]

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            _retrieve_with_sources,
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
        await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="remember this",
                stage="chat",
            ),
        )

        assert calls == ["remember this"]

    @pytest.mark.asyncio
    async def test_post_tool_stage_uses_reduced_context(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: ("## Relevant Memories\n- resume memory", [{"id": "mem1", "type": "memory", "title": "resume memory"}]),
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
                conversation_id="conv_resume",
                execution_id=None,
                user_message="审批后继续",
                stage="post_tool",
            ),
        )

        assert "resume memory" in result
        assert "Personal AI Runtime" in result
        assert "## 待办动作" not in result
        assert "## 近期事件" not in result


class TestEmptyFragmentBehavior:
    @pytest.mark.asyncio
    async def test_empty_actions_and_events_omitted_from_output(self, monkeypatch):
        from app.assembler.context_assembler import ContextAssembler
        from app.context_runtime import FragmentRegistry, RuntimeContext
        from app.core.runtime.governance.fragment_selector import FragmentSelector
        from app.core.runtime.governance.query_analyzer import AnalysisResult
        from app.fragments.register import register_all_fragments

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: ("", []),
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_conversation_messages",
            lambda conversation_id, **kwargs: [],
        )

        registry = FragmentRegistry()
        register_all_fragments(registry)
        selector = FragmentSelector(registry)
        assembler = ContextAssembler()

        fragments = selector.select(AnalysisResult())
        result = await assembler.assemble(
            fragments,
            RuntimeContext(user_message="hi", conversation_id="c1"),
        )

        assert "## 待办动作" not in result
        assert "## 近期事件" not in result
        assert isinstance(result, str)
class TestActionsEventsFragments:
    @pytest.mark.asyncio
    async def test_actions_fragment_format(self, monkeypatch):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.timeline import TimelineContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [
                {"status": "pending", "title": "Task A"},
                {"status": "pending", "title": "Task B"},
            ],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )

        result = await TimelineContextFragment().collect(RuntimeContext())
        assert "## 待办动作" in result.content
        assert "[pending] Task A" in result.content
        assert result.content.count("- [") == 2

    @pytest.mark.asyncio
    async def test_events_fragment_format(self, monkeypatch):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.timeline import TimelineContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [
                {"summary": "Goal created: Learn Rust", "timestamp": "2026-06-18T12:00:00"},
            ],
        )

        result = await TimelineContextFragment().collect(RuntimeContext())
        assert "## 近期事件" in result.content
        assert "Goal created: Learn Rust" in result.content
        assert "(2026-06-18)" in result.content

    @pytest.mark.asyncio
    async def test_actions_empty_returns_empty(self, monkeypatch):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.timeline import TimelineContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )
        result = await TimelineContextFragment().collect(RuntimeContext())
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_events_empty_returns_empty(self, monkeypatch):
        from app.context_runtime import RuntimeContext
        from app.fragments.universal.timeline import TimelineContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )
        result = await TimelineContextFragment().collect(RuntimeContext())
        assert result.content == ""

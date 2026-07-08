"""Tests for Prompt Artifact extraction (Phase 3)."""

from __future__ import annotations

import pytest

from app.chat.prompt_artifact import (
    CODING_RULES_TEMPLATE,
    IDENTITY_ARTIFACT,
    PromptArtifactContext,
    PromptArtifactLoader,
)
from app.config import BASE_DIR


class TestPromptArtifactLoader:
    @pytest.mark.asyncio
    async def test_identity_in_artifact(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=[],
                project_root="/tmp/project",
                stage="chat",
            ),
        )
        assert IDENTITY_ARTIFACT in result
        assert "Personal AI Runtime" in result
        assert "Helpful" in result

    @pytest.mark.asyncio
    async def test_coding_rules_render_project_root(self):
        loader = PromptArtifactLoader()
        project_root = "/custom/project/root"
        result = await loader.load(
            PromptArtifactContext(
                available_tools=[],
                project_root=project_root,
                stage="chat",
            ),
        )
        assert project_root in result
        assert "Coding & project changes:" in result
        assert "Never use absolute paths like /README.md" in result
        assert "shell_exec rules:" in result
        assert "list_directory and read_file" in result
        assert "Protected from agent writes: kernel/" in result

    @pytest.mark.asyncio
    async def test_tool_hints_when_tools_available(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=["check_inbox", "read_inbox_email"],
                project_root="/tmp",
                stage="chat",
            ),
        )
        assert "check_inbox" in result
        assert "read_inbox_email" in result

    @pytest.mark.asyncio
    async def test_tool_hints_absent_when_tools_unavailable(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=[],
                project_root="/tmp",
                stage="chat",
            ),
        )
        assert "walkthrough" not in result
        assert "read_inbox_email to open" not in result

    @pytest.mark.asyncio
    async def test_deterministic_ordering(self):
        loader = PromptArtifactLoader()
        ctx = PromptArtifactContext(
            available_tools=["check_inbox"],
            project_root="/tmp",
            stage="chat",
        )
        first = await loader.load(ctx)
        second = await loader.load(ctx)
        assert first == second
        identity_pos = first.index("Personal AI Runtime")
        coding_pos = first.index("Coding & project changes:")
        hints_pos = first.index("check_inbox")
        assert identity_pos < coding_pos < hints_pos


class TestPromptCompilerArtifactAssembly:
    @pytest.mark.asyncio
    async def test_identity_independent_of_fragment_selection(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        async def _empty_build(self, *args, **kwargs):
            return ""

        monkeypatch.setattr(ContextPipeline, "build", _empty_build)

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="",
                stage="chat",
            ),
        )
        assert "Personal AI Runtime" in result
        assert "Coding & project changes:" in result

    @pytest.mark.asyncio
    async def test_artifact_appears_before_context(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        context_marker = "ZZZ_CONTEXT_FRAGMENT_MARKER"

        async def _stub_build(self, *args, **kwargs):
            return context_marker

        monkeypatch.setattr(ContextPipeline, "build", _stub_build)

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="c1",
                execution_id="e1",
                user_message="hello",
                stage="chat",
            ),
        )

        artifact_pos = result.index("Personal AI Runtime")
        context_pos = result.index(context_marker)
        assert artifact_pos < context_pos
        assert "\n\n---\n" in result

    @pytest.mark.asyncio
    async def test_post_tool_stage_receives_artifact(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        async def _stub_build(self, *args, **kwargs):
            return "CONTEXT_BLOCK"

        monkeypatch.setattr(ContextPipeline, "build", _stub_build)

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="conv_resume",
                execution_id=None,
                user_message="继续",
                stage="post_tool",
            ),
        )

        assert "Personal AI Runtime" in result
        assert CODING_RULES_TEMPLATE.format(project_root=str(BASE_DIR)) in result
        assert "CONTEXT_BLOCK" in result

    @pytest.mark.asyncio
    async def test_full_compile_includes_coding_rules(self, monkeypatch):
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

        assert str(BASE_DIR) in result
        assert "apply_patch" in result
        assert "Personal AI Runtime" in result

"""Tests for Prompt Artifact extraction."""

from __future__ import annotations

import pytest

from app.chat.prompt_artifact import (
    CODING_RULES_TEMPLATE,
    IDENTITY_ARTIFACT,
    PromptArtifactContext,
    PromptArtifactLoader,
    build_policy_tool_notes,
    render_coding_rules,
    should_include_coding_ops,
    should_include_coding_rules,
    tools_for_prompt_hints,
)
from app.config import BASE_DIR

_CODING_TOOLS = ["read_file", "apply_patch", "write_file", "shell_exec"]


class TestPromptFileInvariants:
    """Keep backend/prompts/*.md aligned with governance (single source of truth)."""

    def test_prompts_dir_points_at_backend_prompts(self):
        from app.chat.prompt_artifact import PROMPTS_DIR

        assert PROMPTS_DIR.name == "prompts"
        assert PROMPTS_DIR.parent.name == "backend"
        assert (PROMPTS_DIR / "identity.md").is_file()
        assert (PROMPTS_DIR / "coding_rules.md").is_file()
        assert (PROMPTS_DIR / "coding_rules_ops.md").is_file()

    def test_identity_covers_governance_red_lines(self):
        assert "No side effects without explicit intent" in IDENTITY_ARTIFACT
        assert "capability_policy.json" in IDENTITY_ARTIFACT
        assert "CONSTITUTION" not in IDENTITY_ARTIFACT
        assert "Playwright" not in IDENTITY_ARTIFACT
        # Soft memory attribution (not a rigid marker format).
        assert "低置信度" in IDENTITY_ARTIFACT or "0.6" in IDENTITY_ARTIFACT

    def test_coding_rules_protect_real_paths(self):
        assert "backend/capability_policy.json" in CODING_RULES_TEMPLATE
        assert "backend/app/core/runtime/kernel/" in CODING_RULES_TEMPLATE
        assert "backend/scripts/check_boundary.py" in CODING_RULES_TEMPLATE
        assert "sensitive_router.py" not in CODING_RULES_TEMPLATE
        assert "capability_policy.py" not in CODING_RULES_TEMPLATE
        # MCP/FILESYSTEM ops live in the separate ops appendix.
        assert "FILESYSTEM_" not in CODING_RULES_TEMPLATE
        assert "external_servers" not in CODING_RULES_TEMPLATE

    def test_defaults_match_loaded_artifacts(self):
        from app.chat.prompt_artifact import DEFAULT_CODING_RULES, DEFAULT_IDENTITY

        assert DEFAULT_IDENTITY == IDENTITY_ARTIFACT
        assert DEFAULT_CODING_RULES == CODING_RULES_TEMPLATE


class TestCodingOpsGate:
    def test_ops_keywords(self):
        assert should_include_coding_ops(user_message="请帮我加一个 MCP server")
        assert should_include_coding_ops(user_message="改 FILESYSTEM_ALLOWED_DIRS")
        assert not should_include_coding_ops(user_message="修一下 README 的 typo")

    def test_ops_appended_only_when_relevant(self):
        import asyncio

        loader = PromptArtifactLoader()

        async def _run(msg: str) -> str:
            return await loader.load(
                PromptArtifactContext(
                    available_tools=_CODING_TOOLS,
                    project_root="/tmp",
                    stage="chat",
                    user_message=msg,
                    intent_tags=frozenset({"coding"}),
                ),
            )

        with_ops = asyncio.run(_run("怎么配置 mcp_config.json"))
        without_ops = asyncio.run(_run("修一下函数命名"))
        assert "Ops notes" in with_ops
        assert "external_servers" in with_ops
        assert "Ops notes" not in without_ops


class TestPolicyToolNotes:
    def test_notes_include_needs_user_and_ingestion(self):
        notes = build_policy_tool_notes()
        assert "write_file" in notes
        assert "shell_exec" in notes
        assert "check_inbox" in notes
        assert "fetch_url" in notes


class TestRenderCodingRules:
    def test_replaces_project_root(self):
        assert render_coding_rules("root={project_root}", "/tmp/p") == "root=/tmp/p"

    def test_ignores_other_braces(self):
        template = 'Use {project_root} and keep {"json": true}'
        assert render_coding_rules(template, "/x") == 'Use /x and keep {"json": true}'


class TestCodingRulesGate:
    def test_skipped_on_brief(self):
        assert not should_include_coding_rules(
            stage="brief",
            intent_tags=frozenset({"coding"}),
            available_tools=_CODING_TOOLS,
        )

    def test_included_on_coding_intent(self):
        assert should_include_coding_rules(
            stage="chat",
            intent_tags=frozenset({"coding"}),
            available_tools=_CODING_TOOLS,
        )

    def test_skipped_without_coding_intent_on_chat(self):
        assert not should_include_coding_rules(
            stage="chat",
            intent_tags=frozenset({"mail"}),
            available_tools=_CODING_TOOLS,
        )

    def test_included_on_post_tool_when_coding_tools_present(self):
        assert should_include_coding_rules(
            stage="post_tool",
            intent_tags=frozenset(),
            available_tools=_CODING_TOOLS,
        )

    def test_skipped_without_coding_tools(self):
        assert not should_include_coding_rules(
            stage="chat",
            intent_tags=frozenset({"coding"}),
            available_tools=["check_inbox"],
        )


class TestHintToolGate:
    def test_brief_drops_all(self):
        assert tools_for_prompt_hints(
            stage="brief",
            intent_tags=frozenset({"mail"}),
            available_tools=["check_inbox"],
        ) == set()

    def test_chat_without_mail_drops_mail_hints(self):
        tools = tools_for_prompt_hints(
            stage="chat",
            intent_tags=frozenset({"coding"}),
            available_tools=["check_inbox", "read_file"],
        )
        assert "check_inbox" not in tools
        assert "read_file" in tools

    def test_mail_intent_keeps_mail_hints(self):
        tools = tools_for_prompt_hints(
            stage="chat",
            intent_tags=frozenset({"mail"}),
            available_tools=["check_inbox"],
        )
        assert "check_inbox" in tools

    def test_post_tool_keeps_mail_hints(self):
        tools = tools_for_prompt_hints(
            stage="post_tool",
            intent_tags=frozenset(),
            available_tools=["check_inbox"],
        )
        assert "check_inbox" in tools


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
        assert "Gated side-effect tools" in result
        assert "write_file" in result

    @pytest.mark.asyncio
    async def test_coding_rules_render_project_root(self):
        loader = PromptArtifactLoader()
        project_root = "/custom/project/root"
        result = await loader.load(
            PromptArtifactContext(
                available_tools=_CODING_TOOLS,
                project_root=project_root,
                stage="chat",
                intent_tags=frozenset({"coding"}),
            ),
        )
        assert project_root in result
        assert "Coding & project changes:" in result
        assert "Never use absolute paths like /README.md" in result
        assert "shell_exec rules:" in result
        assert "list_directory and read_file" in result
        assert "Protected from agent writes:" in result
        assert "backend/app/core/runtime/kernel/" in result
        assert "backend/capability_policy.json" in result
        assert "sensitive_router.py" not in result

    @pytest.mark.asyncio
    async def test_coding_rules_absent_without_coding_intent(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=_CODING_TOOLS,
                project_root="/tmp",
                stage="chat",
                intent_tags=frozenset({"mail"}),
            ),
        )
        assert "Coding & project changes:" not in result

    @pytest.mark.asyncio
    async def test_brief_is_identity_only(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=_CODING_TOOLS + ["check_inbox"],
                project_root="/tmp",
                stage="brief",
                intent_tags=frozenset({"coding", "mail"}),
            ),
        )
        assert "Personal AI Runtime" in result
        assert "Coding & project changes:" not in result
        assert "walkthrough" not in result

    @pytest.mark.asyncio
    async def test_tool_hints_when_mail_intent(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=["check_inbox", "read_inbox_email"],
                project_root="/tmp",
                stage="chat",
                intent_tags=frozenset({"mail"}),
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
    async def test_tool_hints_absent_without_mail_intent(self):
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=["check_inbox", "read_inbox_email"],
                project_root="/tmp",
                stage="chat",
                intent_tags=frozenset({"goals"}),
            ),
        )
        assert "walkthrough" not in result

    @pytest.mark.asyncio
    async def test_deterministic_ordering(self):
        loader = PromptArtifactLoader()
        ctx = PromptArtifactContext(
            available_tools=["check_inbox", *_CODING_TOOLS],
            project_root="/tmp",
            stage="chat",
            intent_tags=frozenset({"coding", "mail"}),
        )
        first = await loader.load(ctx)
        second = await loader.load(ctx)
        assert first == second
        identity_pos = first.index("Personal AI Runtime")
        policy_pos = first.index("Gated side-effect tools")
        coding_pos = first.index("Coding & project changes:")
        hints_pos = first.index("The UI renders check_inbox results as a table")
        assert identity_pos < policy_pos < coding_pos < hints_pos

    @pytest.mark.asyncio
    async def test_custom_coding_rules_with_extra_braces(self, monkeypatch):
        from app.chat import prompt_artifact as pa

        monkeypatch.setattr(
            pa,
            "_load_runtime_prompt",
            lambda key: (
                "Root {project_root}; example {\"a\": 1}"
                if key == "coding_rules"
                else None
            ),
        )
        loader = PromptArtifactLoader()
        result = await loader.load(
            PromptArtifactContext(
                available_tools=_CODING_TOOLS,
                project_root="/safe",
                stage="chat",
                intent_tags=frozenset({"coding"}),
            ),
        )
        assert "Root /safe; example {\"a\": 1}" in result


class TestPromptCompilerArtifactAssembly:
    @pytest.mark.asyncio
    async def test_identity_independent_of_fragment_selection(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        async def _empty_build(self, *args, **kwargs):
            return ""

        monkeypatch.setattr(ContextPipeline, "build", _empty_build)
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [
                {"function": {"name": n}} for n in _CODING_TOOLS
            ],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="请修复这个 bug",
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
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [{"function": {"name": n}} for n in _CODING_TOOLS],
        )

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
        assert CODING_RULES_TEMPLATE.replace("{project_root}", str(BASE_DIR)) in result
        assert "CONTEXT_BLOCK" in result

    @pytest.mark.asyncio
    async def test_compile_shares_intent_tags_with_pipeline(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        captured: dict = {}

        async def _capture_build(self, *args, **kwargs):
            captured.update(kwargs)
            return ""

        monkeypatch.setattr(ContextPipeline, "build", _capture_build)
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [{"function": {"name": n}} for n in _CODING_TOOLS],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="请修复这个 bug",
                stage="chat",
            ),
        )
        assert "coding" in captured.get("intent_tags", frozenset())

    @pytest.mark.asyncio
    async def test_compile_passes_remaining_budget_to_pipeline(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.agents.token_counter import count_text_tokens
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        captured: dict = {}

        async def _capture_build(self, *args, **kwargs):
            captured.update(kwargs)
            return ""

        monkeypatch.setattr(ContextPipeline, "build", _capture_build)
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        total_budget = 5000
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="你好",
                stage="chat",
            ),
            budget=total_budget,
        )
        expected = total_budget - count_text_tokens(result) - count_text_tokens("\n\n---\n")
        assert captured.get("budget") == expected

    @pytest.mark.asyncio
    async def test_chat_skips_coding_rules_without_coding_intent(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        async def _empty_build(self, *args, **kwargs):
            return ""

        monkeypatch.setattr(ContextPipeline, "build", _empty_build)
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [{"function": {"name": n}} for n in _CODING_TOOLS],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="今天天气怎么样",
                stage="chat",
            ),
        )
        assert "Personal AI Runtime" in result
        assert "Coding & project changes:" not in result

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
        monkeypatch.setattr(
            "app.chat.prompt_compiler.kernel.list_capability_definitions",
            lambda: [{"function": {"name": n}} for n in _CODING_TOOLS],
        )

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="",
                execution_id=None,
                user_message="请重构这段代码",
                stage="chat",
            ),
        )

        assert str(BASE_DIR) in result
        assert "apply_patch" in result
        assert "Personal AI Runtime" in result

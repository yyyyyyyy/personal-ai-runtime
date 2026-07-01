"""Architecture tests — Context Policy primitive (Phase 8)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.context_runtime import FragmentRegistry
from app.core.runtime.governance.context_policy import (
    CompilePlan,
    CompileRequest,
    DefaultContextPolicy,
)
from app.core.runtime.governance.fragment_selector import FragmentSelector
from app.core.runtime.governance.query_analyzer import AnalysisResult, QueryAnalyzer
from app.core.runtime.principal import Principal
from app.fragments.register import register_all_fragments

_PIPELINE_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "core"
    / "runtime"
    / "governance"
    / "context_pipeline.py"
)

_PARITY_MESSAGES = [
    "",
    "hello",
    "帮我查一下邮件",
    "今天有什么会议",
    "规划一下下周任务",
    "复盘本周工作",
    "查知识库文档",
]


def _legacy_fragment_ids(registry: FragmentRegistry, message: str) -> list[str]:
    analysis = QueryAnalyzer().analyze(message)
    selected = FragmentSelector(registry).select(analysis)
    return [f.id for f in selected]


def _policy_fragment_ids(
    registry: FragmentRegistry,
    message: str,
    *,
    stage: str = "chat",
) -> list[str]:
    policy = DefaultContextPolicy(registry)
    plan = policy.evaluate(CompileRequest(user_message=message, stage=stage))
    return [f.id for f in plan.selected_fragments]


class TestPolicyPrimitivesExist:
    def test_compile_request_fields(self):
        req = CompileRequest(
            user_message="hi",
            conversation_id="c1",
            execution_id="e1",
            stage="post_tool",
            principal=Principal.user(),
            context_budget=16000,
        )
        assert req.user_message == "hi"
        assert req.conversation_id == "c1"
        assert req.execution_id == "e1"
        assert req.stage == "post_tool"
        assert req.principal is not None
        assert req.context_budget == 16000

    def test_compile_plan_fields(self):
        plan = CompilePlan(
            selected_fragments=[],
            context_budget=32000,
            policy_name="default",
            analysis_result=AnalysisResult(tags={"mail"}),
        )
        assert plan.policy_name == "default"
        assert plan.analysis_result is not None
        assert "mail" in plan.analysis_result.tags

    def test_default_context_policy_exists(self):
        policy = DefaultContextPolicy()
        assert policy.POLICY_NAME == "default"
        assert hasattr(policy, "evaluate")


class TestPipelineDependsOnPolicy:
    def test_pipeline_constructor_accepts_policy(self):
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        registry = FragmentRegistry()
        policy = DefaultContextPolicy(registry)
        pipeline = ContextPipeline(registry, policy=policy)
        assert pipeline._policy is policy

    def test_pipeline_does_not_own_selector(self):
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        source = inspect.getsource(ContextPipeline)
        assert "FragmentSelector" not in source
        assert "QueryAnalyzer" not in source

    def test_pipeline_module_imports_policy_not_selector(self):
        tree = ast.parse(_PIPELINE_PATH.read_text(encoding="utf-8"), filename=str(_PIPELINE_PATH))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert "app.core.runtime.governance.context_policy" in imported
        assert "app.core.runtime.governance.fragment_selector" not in imported
        assert "app.core.runtime.governance.query_analyzer" not in imported


class TestBehavioralParity:
    @pytest.mark.parametrize("message", _PARITY_MESSAGES)
    def test_chat_stage_matches_legacy_selection(self, message: str):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        assert _policy_fragment_ids(registry, message, stage="chat") == _legacy_fragment_ids(
            registry, message,
        )

    def test_default_policy_preserves_analysis_result(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        policy = DefaultContextPolicy(registry)
        plan = policy.evaluate(CompileRequest(user_message="帮我查邮件", stage="chat"))
        assert plan.analysis_result is not None
        assert "mail" in plan.analysis_result.tags

    def test_chat_stage_preserves_budget(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        policy = DefaultContextPolicy(registry)
        plan = policy.evaluate(
            CompileRequest(user_message="hi", context_budget=12000, stage="chat"),
        )
        assert plan.context_budget == 12000

    @pytest.mark.asyncio
    async def test_pipeline_build_from_request_matches_build(self, monkeypatch):
        from app.assembler.context_assembler import AssemblyResult
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        registry = FragmentRegistry()
        register_all_fragments(registry)

        captured: list = []

        async def _fake_assemble_with_sources(fragments, ctx, budget=32000):
            captured.append(([f.id for f in fragments], ctx.user_message, budget))
            return AssemblyResult(system_prompt="assembled", sources=[])

        pipeline = ContextPipeline(registry)
        monkeypatch.setattr(pipeline._assembler, "assemble_with_sources", _fake_assemble_with_sources)

        via_build = await pipeline.build(
            user_message="查邮件",
            conversation_id="c1",
            execution_id="e1",
            budget=8000,
            stage="chat",
        )
        via_request = await pipeline.build_from_request(
            CompileRequest(
                user_message="查邮件",
                conversation_id="c1",
                execution_id="e1",
                context_budget=8000,
                stage="chat",
            ),
        )

        assert via_build == "assembled"
        assert via_request == "assembled"
        assert len(captured) == 2
        assert captured[0][0] == captured[1][0]
        assert captured[0][2] == 8000


class TestStageInfluence:
    def test_chat_differs_from_post_tool(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        chat_ids = set(_policy_fragment_ids(registry, "hello", stage="chat"))
        post_tool_ids = set(_policy_fragment_ids(registry, "hello", stage="post_tool"))
        assert chat_ids != post_tool_ids
        assert "core.timeline" in chat_ids
        assert "core.timeline" not in post_tool_ids
        assert "core.memory" in post_tool_ids

    def test_chat_differs_from_brief(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        chat_ids = set(_policy_fragment_ids(registry, "hello", stage="chat"))
        brief_ids = set(_policy_fragment_ids(registry, "hello", stage="brief"))
        assert chat_ids != brief_ids
        assert "core.conversation_state" in chat_ids
        assert "core.conversation_state" not in brief_ids
        assert "core.goals" in brief_ids
        assert "calendar.today" in brief_ids

    def test_post_tool_includes_scenario_for_mail(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        ids = set(_policy_fragment_ids(registry, "查邮件", stage="post_tool"))
        assert "mail.recent_emails" in ids
        assert "core.timeline" not in ids

    def test_post_tool_budget_capped(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        plan = DefaultContextPolicy(registry).evaluate(
            CompileRequest(user_message="hi", context_budget=32000, stage="post_tool"),
        )
        assert plan.context_budget == 24000

    def test_brief_budget_capped(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        plan = DefaultContextPolicy(registry).evaluate(
            CompileRequest(user_message="今日简报", context_budget=32000, stage="brief"),
        )
        assert plan.context_budget == 16000


class TestCompileRequestPropagation:
    @pytest.mark.asyncio
    async def test_prompt_compiler_passes_stage_to_pipeline(self, monkeypatch):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        captured: list[str] = []

        async def _capture_build(*args, **kwargs):
            captured.append(kwargs.get("stage", args[0] if args else "missing"))
            return ""

        pipeline = ContextPipeline(FragmentRegistry())
        monkeypatch.setattr(pipeline, "build", _capture_build)
        compiler = PromptCompiler(pipeline=pipeline)
        await compiler.compile(
            CompileContext(
                conversation_id="c1",
                execution_id="e1",
                user_message="hi",
                stage="post_tool",
            ),
        )
        assert captured == ["post_tool"]


class TestPolicyObservability:
    def test_compile_plan_observation_dict(self):
        registry = FragmentRegistry()
        register_all_fragments(registry)
        plan = DefaultContextPolicy(registry).evaluate(
            CompileRequest(user_message="规划下周", stage="chat"),
        )
        obs = plan.to_observation_dict()
        assert obs["policy_name"] == "default"
        assert obs["stage"] == "chat"
        assert "core.goals" in obs["selected_fragment_ids"]
        assert obs["rationale"]
        assert "planning" in obs["tags"] or "planning" in str(obs["tags"])

    @pytest.mark.asyncio
    async def test_pipeline_exposes_last_compile_plan(self, monkeypatch):
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        registry = FragmentRegistry()
        register_all_fragments(registry)
        pipeline = ContextPipeline(registry)

        async def _fake_assemble(fragments, ctx, budget=32000):
            return "ok"

        monkeypatch.setattr(pipeline._assembler, "assemble", _fake_assemble)
        assert pipeline.last_compile_plan() is None

        await pipeline.build_from_request(
            CompileRequest(user_message="hello", stage="brief"),
        )
        plan = pipeline.last_compile_plan()
        assert plan is not None
        assert plan.stage == "brief"
        assert plan.selected_fragment_ids
        assert plan.to_observation_dict()["stage"] == "brief"

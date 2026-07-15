"""Architectural tests — Policy coverage enforcement.

Every context compilation path must flow through ContextPolicy.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parent.parent / "app"
_GOVERNANCE_ROOT = _APP_ROOT / "core" / "runtime" / "governance"

# Known compilation entrypoints: file (relative to app/) → expected stage
_POLICY_COVERAGE_MATRIX: dict[str, str] = {
    "core/agents/handlers/chat_handler.py": "chat",
    "core/agents/brain_llm_ops.py": "post_tool",
}

# PromptCompiler is the LLM-facing compile facade for chat stages
_PROMPT_COMPILER_ENTRYPOINTS = frozenset({
    "core/agents/handlers/chat_handler.py",
    "core/agents/brain_llm_ops.py",
})

# Non-LLM paths may call ContextPipeline directly (still via Policy)
_DIRECT_PIPELINE_ENTRYPOINTS = frozenset()


def _read_source(rel_path: str) -> str:
    return (_APP_ROOT / rel_path).read_text(encoding="utf-8")


def _collect_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


class TestPolicyCoverageMatrix:
    """Every known compilation entrypoint maps to a Policy stage."""

    @pytest.mark.parametrize("rel_path,stage", list(_POLICY_COVERAGE_MATRIX.items()))
    def test_entrypoint_declares_stage(self, rel_path: str, stage: str):
        source = _read_source(rel_path)
        assert f'stage="{stage}"' in source or f"stage='{stage}'" in source, (
            f"{rel_path} must use stage={stage!r}"
        )

    @pytest.mark.parametrize("rel_path", list(_POLICY_COVERAGE_MATRIX.keys()))
    def test_entrypoint_uses_policy_path(self, rel_path: str):
        source = _read_source(rel_path)
        uses_compiler = "prompt_compiler" in source
        uses_pipeline = "context_pipeline" in source or "ContextPipeline" in source
        assert uses_compiler or uses_pipeline, (
            f"{rel_path} must route through PromptCompiler or ContextPipeline"
        )



class TestNoAlternateSelectors:
    """FragmentSelector must only be owned by DefaultContextPolicy."""

    def test_fragment_selector_imports_confined_to_governance(self):
        violations: list[str] = []
        for path in _APP_ROOT.rglob("*.py"):
            if path.name == "fragment_selector.py":
                continue
            rel = path.relative_to(_APP_ROOT).as_posix()
            if not rel.startswith("core/runtime/governance/"):
                for lineno, module in _collect_imports(path):
                    if module and "fragment_selector" in module:
                        violations.append(f"{rel}:{lineno} imports {module}")
        assert not violations, "\n".join(violations)

    def test_query_analyzer_imports_confined_to_governance(self):
        violations: list[str] = []
        for path in _APP_ROOT.rglob("*.py"):
            if path.name == "query_analyzer.py":
                continue
            rel = path.relative_to(_APP_ROOT).as_posix()
            if not rel.startswith("core/runtime/governance/"):
                for lineno, module in _collect_imports(path):
                    if module and "query_analyzer" in module:
                        violations.append(f"{rel}:{lineno} imports {module}")
        assert not violations, "\n".join(violations)


class TestPromptCompilerRoutesThroughPipeline:
    def test_prompt_compiler_does_not_import_selector(self):
        source = _read_source("chat/prompt_compiler.py")
        assert "FragmentSelector" not in source
        assert "QueryAnalyzer" not in source
        assert "context_pipeline" in source or "ContextPipeline" in source


class TestCompilePlanVisibility:
    @pytest.mark.asyncio
    async def test_pipeline_last_compile_plan_after_brief(self, monkeypatch):
        from app.assembler.context_assembler import AssemblyResult
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline
        from app.core.runtime.governance.context_policy import CompileRequest
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        register_all_fragments(registry)
        pipeline = ContextPipeline(registry)

        async def _fake_assemble_with_sources(fragments, ctx, budget=32000):
            return AssemblyResult(system_prompt="brief-context", sources=[])

        monkeypatch.setattr(pipeline._assembler, "assemble_with_sources", _fake_assemble_with_sources)

        text = await pipeline.build_from_request(
            CompileRequest(user_message="今日简报", stage="brief"),
        )
        plan = pipeline.last_compile_plan()

        assert text == "brief-context"
        assert plan is not None
        assert plan.stage == "brief"
        obs = plan.to_observation_dict()
        assert obs["stage"] == "brief"
        assert obs["selected_fragment_ids"]
        assert obs["rationale"]


class TestCoverageCompleteness:
    """Documented non-policy paths must not assemble fragment context."""

    def test_brain_synthesis_does_not_recompile_context(self):
        source = _read_source("core/agents/brain_llm_ops.py")
        assert "synthesize_from_tool_results" in source
        synth_start = source.index("async def synthesize_from_tool_results")
        synth_body = source[synth_start:synth_start + 800]
        assert "prompt_compiler" not in synth_body
        assert "context_pipeline" not in synth_body

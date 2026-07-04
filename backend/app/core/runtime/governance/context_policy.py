"""Context Policy — Runtime primitive for context compilation planning.

    CompileRequest → ContextPolicy.evaluate() → CompilePlan

Policy owns selection decisions. Pipeline executes the plan.

Execution-Aware Context Policy
Capability-Aware Governance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from app.context_runtime import ContextFragment, FragmentRegistry, fragment_registry
from app.core.runtime.execution import Principal
from app.core.runtime.governance.fragment_selector import FragmentSelector
from app.core.runtime.governance.query_analyzer import AnalysisResult, QueryAnalyzer

if TYPE_CHECKING:
    pass

_DEFAULT_CONTEXT_BUDGET = 32000

CompileStage = Literal["chat", "post_tool", "brief"]

_STAGE_BUDGET_CAP: dict[CompileStage, int | None] = {
    "chat": None,
    "post_tool": 24000,
    "brief": 16000,
}

_STAGE_RATIONALE: dict[CompileStage, str] = {
    "chat": "Full Core + Priority + Scenario tiers (default conversational context)",
    "post_tool": "Reduced set: memory + conversation state + scenario tags for tool continuation",
    "brief": "Summary-oriented: goals, calendar, world news; no conversation fragments",
}

# Fragment tag → scoring reason label (shared)
_TAG_LABELS: dict[str, str] = {
    "calendar": "CalendarFragment",
    "mail": "MailFragment",
    "goals": "GoalFragment",
    "planning": "PlanFragment",
    "memory": "MemoryFragment",
}


@dataclass(frozen=True)
class CompileRequest:
    """A context compilation request.

    Pure by design — contains only user intent information. Runtime
    state is delivered separately via context snapshots.
    """

    user_message: str
    conversation_id: str = ""
    execution_id: str = ""
    stage: CompileStage = "chat"
    principal: Principal | None = None
    context_budget: int = _DEFAULT_CONTEXT_BUDGET


@dataclass
class CompilePlan:
    """Output of policy evaluation — sufficient to drive assembly."""

    selected_fragments: list[ContextFragment]
    context_budget: int = _DEFAULT_CONTEXT_BUDGET
    policy_name: str = "default"
    analysis_result: AnalysisResult | None = None
    stage: CompileStage = "chat"
    selected_fragment_ids: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
    policy_reasons: list[str] = field(default_factory=list)

    def to_observation_dict(self) -> dict:
        """Inspectable policy decision metadata."""
        return {
            "policy_name": self.policy_name,
            "stage": self.stage,
            "context_budget": self.context_budget,
            "selected_fragment_ids": list(self.selected_fragment_ids),
            "rationale": self.rationale,
            "tags": sorted(self.analysis_result.tags) if self.analysis_result else [],
            "policy_reasons": self.policy_reasons,
        }


class ContextPolicy(Protocol):
    """Evaluates a compile request and returns a plan.

    Accepts optional execution_context and capability_context.
    Backward-compatible — DefaultContextPolicy ignores both.
    """

    def evaluate(
        self,
        request: CompileRequest,
        *,
        execution_context: object | None = None,
        capability_context: object | None = None,
    ) -> CompilePlan: ...


class DefaultContextPolicy:
    """Stage-aware default policy — chat preserves legacy selection behavior.

    Does NOT consume any runtime contexts. This is the active production
    policy used by ContextPipeline.
    """

    POLICY_NAME = "default"

    def __init__(self, registry: FragmentRegistry | None = None):
        self._registry = registry or fragment_registry
        self._analyzer = QueryAnalyzer()
        self._selector = FragmentSelector(self._registry)

    def evaluate(self, request: CompileRequest) -> CompilePlan:
        analysis = self._analyzer.analyze(request.user_message)
        fragments = self._selector.select_for_stage(analysis, request.stage)
        budget = _resolve_stage_budget(request.stage, request.context_budget)
        fragment_ids = tuple(f.id for f in fragments)
        return CompilePlan(
            selected_fragments=fragments,
            context_budget=budget,
            policy_name=self.POLICY_NAME,
            analysis_result=analysis,
            stage=request.stage,
            selected_fragment_ids=fragment_ids,
            rationale=_STAGE_RATIONALE[request.stage],
        )



def _resolve_stage_budget(stage: CompileStage, requested: int) -> int:
    cap = _STAGE_BUDGET_CAP.get(stage)
    if cap is None:
        return requested
    return min(requested, cap)


default_context_policy = DefaultContextPolicy()

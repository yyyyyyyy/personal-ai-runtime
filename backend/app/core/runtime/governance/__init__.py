"""Runtime governance — context policy, query analysis, fragment selection, assembly.

Active production components only.
Archived: capability_context, execution_context (snapshot builders no longer consumed
          by DefaultContextPolicy), GovernancePolicy, GovernancePolicyEngine
          → archive/governance_phase12/
"""

from app.core.runtime.governance.context_pipeline import ContextPipeline, context_pipeline
from app.core.runtime.governance.context_policy import (
    CompilePlan,
    CompileRequest,
    CompileStage,
    ContextPolicy,
    DefaultContextPolicy,
    default_context_policy,
)
from app.core.runtime.governance.fragment_selector import (
    CORE_TIER_FRAGMENT_IDS,
    FragmentSelector,
)
from app.core.runtime.governance.query_analyzer import AnalysisResult, QueryAnalyzer

__all__ = [
    "AnalysisResult",
    "CORE_TIER_FRAGMENT_IDS",
    "CompilePlan",
    "CompileRequest",
    "CompileStage",
    "ContextPipeline",
    "ContextPolicy",
    "DefaultContextPolicy",
    "FragmentSelector",
    "QueryAnalyzer",
    "context_pipeline",
    "default_context_policy",
]

"""Runtime governance — context policy, query analysis, fragment selection, assembly.

Active production components only.
Archived: GovernancePolicy, GovernancePolicyEngine, composable policy modules
          → archive/governance_phase12/
"""

from app.core.runtime.governance.capability_context import (
    ALL_KNOWN_CAPABILITIES,
    CapabilityContext,
    CapabilityContextProvider,
    fragment_required_capabilities,
)
from app.core.runtime.governance.context_pipeline import ContextPipeline, context_pipeline
from app.core.runtime.governance.context_policy import (
    CompilePlan,
    CompileRequest,
    CompileStage,
    ContextPolicy,
    DefaultContextPolicy,
    default_context_policy,
)
from app.core.runtime.governance.execution_context import (
    ExecutionContextProvider,
    GovernanceExecutionContext,
)
from app.core.runtime.governance.fragment_selector import (
    CORE_TIER_FRAGMENT_IDS,
    FragmentSelector,
    reachable_fragment_ids,
)
from app.core.runtime.governance.query_analyzer import AnalysisResult, QueryAnalyzer

__all__ = [
    "ALL_KNOWN_CAPABILITIES",
    "AnalysisResult",
    "CORE_TIER_FRAGMENT_IDS",
    "CapabilityContext",
    "CapabilityContextProvider",
    "CompilePlan",
    "CompileRequest",
    "CompileStage",
    "ContextPipeline",
    "ContextPolicy",
    "DefaultContextPolicy",
    "ExecutionContextProvider",
    "GovernanceExecutionContext",
    "FragmentSelector",
    "QueryAnalyzer",
    "context_pipeline",
    "default_context_policy",
    "fragment_required_capabilities",
    "reachable_fragment_ids",
]

"""ContextPipeline — policy executor for context assembly.

    CompileRequest → ContextPolicy → CompilePlan → ContextAssembler → System Prompt

    Execution-Aware Pipeline:
    Pipeline builds a GovernanceExecutionContext snapshot before each
    policy evaluation. The snapshot includes recent fragment history,
    tool activity, and event log data. This snapshot is passed to the
    policy (read-only) and never read by Fragments or Assembler.

    Capability-Aware Pipeline:
    Pipeline also builds a CapabilityContext snapshot and passes it
    to the policy. The snapshot describes available system capabilities,
    runtime mode, and granted permissions.

    Citation Tracking:
    Pipeline tracks sources (memories, knowledge docs) used during
    context assembly and stores them for SSE emission.

Usage:
    pipeline = ContextPipeline()
    system_prompt = await pipeline.build(user_message, conv_id)
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque

from app.assembler.context_assembler import ContextAssembler
from app.context_runtime import (
    FragmentRegistry,
    RuntimeContext,
    fragment_registry,
)
from app.core.runtime.governance.context_policy import (
    CompilePlan,
    CompileRequest,
    CompileStage,
    ContextPolicy,
    DefaultContextPolicy,
)
from app.core.runtime.principal import Principal

_MAX_RECENT_FRAGMENT_HISTORY = 5

# ── Source Registry — citation tracking for SSE emission ────────────────
# conversation_id -> (sources, timestamp)
# TTL-based cleanup prevents memory leaks when SSE connections drop before get_sources().
_SOURCE_TTL_SECONDS = 300  # 5 minutes
_source_registry: dict[str, tuple[list[dict], float]] = {}
_source_registry_lock = threading.Lock()  # guard for concurrent SSE streams


def get_sources(conversation_id: str) -> list[dict]:
    """Retrieve and clear sources for a conversation (one-shot read). Thread-safe."""
    with _source_registry_lock:
        entry = _source_registry.pop(conversation_id, None)
    if entry is None:
        return []
    sources, ts = entry
    if _time.monotonic() - ts > _SOURCE_TTL_SECONDS:
        return []
    return sources


def _store_sources(conversation_id: str, sources: list[dict]) -> None:
    """Store sources for later retrieval by SSE stream. Thread-safe.

    Also purges expired entries to prevent unbounded growth.
    """
    # Lazy cleanup: remove expired entries on every write
    now = _time.monotonic()
    with _source_registry_lock:
        expired = [k for k, (_, ts) in _source_registry.items() if now - ts > _SOURCE_TTL_SECONDS]
        for k in expired:
            _source_registry.pop(k, None)

        if sources:
            _source_registry[conversation_id] = (sources, now)


class ContextPipeline:
    """Registers fragments and executes context policy plans.

    Maintains a rolling history of recently injected fragment IDs and
    optionally builds a GovernanceExecutionContext for runtime-aware
    policy decisions. Also builds a CapabilityContext for capability-aware
    policy decisions.
    """

    def __init__(
        self,
        registry: FragmentRegistry | None = None,
        policy: ContextPolicy | None = None,
    ):
        self._registry = registry or fragment_registry
        self._policy = policy or DefaultContextPolicy(self._registry)
        self._assembler = ContextAssembler()
        self._last_plan: CompilePlan | None = None
        self._recent_fragment_ids: deque[str] = deque(maxlen=_MAX_RECENT_FRAGMENT_HISTORY)

        self._ensure_fragments_registered()

    def _ensure_fragments_registered(self) -> None:
        """确保所有 Fragment 已注册（幂等）。"""
        try:
            from app.fragments.register import register_all_fragments

            register_all_fragments(self._registry)
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "ContextPipeline: DB may not be available", exc_info=True
            )

    def last_compile_plan(self) -> CompilePlan | None:
        """Return the most recent CompilePlan produced by this pipeline."""
        return self._last_plan

    def _record_fragment_ids(self, fragment_ids: tuple[str, ...]) -> None:
        for fid in fragment_ids:
            if fid not in self._recent_fragment_ids:
                self._recent_fragment_ids.append(fid)

    async def build_from_request(self, request: CompileRequest) -> str:
        """Compile context from a structured request."""
        # Evaluate policy
        plan = self._policy.evaluate(request)
        self._last_plan = plan
        self._record_fragment_ids(plan.selected_fragment_ids)

        ctx = RuntimeContext(
            user_message=request.user_message,
            conversation_id=request.conversation_id,
            execution_id=request.execution_id,
        )
        # Use assemble_with_sources for citation tracking
        assembly_result = await self._assembler.assemble_with_sources(
            plan.selected_fragments,
            ctx,
            budget=plan.context_budget,
        )
        _store_sources(request.conversation_id, assembly_result.sources)
        return assembly_result.system_prompt

    async def build(
        self,
        user_message: str,
        conversation_id: str = "",
        execution_id: str = "",
        budget: int = 32000,
        *,
        stage: CompileStage = "chat",
        principal: Principal | None = None,
    ) -> str:
        """消息 → policy → 组装 → System Prompt（向后兼容入口）。"""
        request = CompileRequest(
            user_message=user_message,
            conversation_id=conversation_id,
            execution_id=execution_id,
            stage=stage,
            principal=principal,
            context_budget=budget,
        )
        return await self.build_from_request(request)


# Global singleton
context_pipeline = ContextPipeline()
# registered in RuntimeContainer.inventory()


def reset_source_registry() -> None:
    """Clear the citation source registry — for test isolation."""
    with _source_registry_lock:
        _source_registry.clear()

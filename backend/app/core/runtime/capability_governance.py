"""CapabilityGovernance — unified capability authorization and policy management.

v0.4.0: Merged from CapabilityGateway + CapabilityPolicy + ApprovalEngine.
Single module for policy seeding, risk lookup, 4-gate authorization, approval
queries, and external tool registration. Eliminates the approval dual-path
(FACT-35).

Gate 1: policy_events projection (forbidden check)
Gate 2: grant_events projection (principal authorization)
Gate 3: pre-approved fast path (consume pre-approved approval)
Gate 4: risk assessment + approval deferral
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.runtime.principal import Principal

if TYPE_CHECKING:

    from app.core.runtime.kernel.kernel import Kernel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapabilityDecision:
    """Result of a capability authorization check."""

    decision: str  # "allow" | "deny" | "defer"
    reason: str
    approval_id: str | None = None


# ── Flow classification helpers (ex-approval enrichment) ─────────

_CORR_PREFIX_MAP: list[tuple[str, str]] = [
    ("chat_", "对话"),
    ("sched_", "定时任务"),
    ("trigger_", "定时任务"),
]
_CORR_EXACT_MAP: dict[str, tuple[str, str]] = {
    "approval-resolve-test": ("测试", "审批解析测试"),
}


def _classify_flow(corr_id: str, task_id: str | None, task_map: dict[str, str]) -> str:
    if task_id and task_id in task_map:
        return "任务"
    for prefix, label in _CORR_PREFIX_MAP:
        if corr_id.startswith(prefix):
            return label
    exact = _CORR_EXACT_MAP.get(corr_id)
    if exact:
        return exact[0]
    return "系统" if corr_id else "未知"


def _label_flow(corr_id: str, task_id: str | None, task_map: dict[str, str]) -> str:
    if task_id and task_id in task_map:
        return task_map[task_id]
    for prefix, label in _CORR_PREFIX_MAP:
        if corr_id.startswith(prefix):
            return f"{label} ({corr_id})"
    exact = _CORR_EXACT_MAP.get(corr_id)
    if exact:
        return exact[1]
    return corr_id or ""


class CapabilityGovernance:
    """Unified capability authorization, policy, and approval management.

    Combines the responsibilities of the former CapabilityGateway,
    CapabilityPolicy, and ApprovalEngine into a single governance module.
    """

    def __init__(self):
        self._external_auto_allow: set[str] = set()
        self._external_needs_user: set[str] = set()
        self._external_forbidden: set[str] = set()
        self._kernel: Kernel | None = None
        # Instance-level cache for policy_events risk lookups so the hot
        # capability-decision path does not hit the DB on every tool call.
        # Invalidated by any policy mutation (seed/register/revoke).
        self._risk_cache: dict[tuple[str, bool], str] = {}

    # ── Seed (startup) ─────────────────────────────────────────────

    def seed_from_json(self, kernel: Kernel) -> None:
        """Emit PolicyCreated events from capability_policy.json seed."""
        from pathlib import Path

        from app.config import settings

        self._kernel = kernel
        path = Path(settings.capability_policy_path)
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))

        for name in data.get("forbidden", []):
            self._ensure_policy(kernel, name, "forbidden")
        for name in data.get("needs_user", []):
            self._ensure_policy(kernel, name, "high")
        for name in data.get("auto_allow", []):
            self._ensure_policy(kernel, name, "low")

    def _ensure_policy(self, kernel: Kernel, capability: str, risk: str) -> None:
        existing = kernel.query_state("policy_events", capability=capability, limit=1)
        if existing:
            return
        kernel.emit_event(
            "PolicyCreated", "policy", f"policy_{capability}",
            payload={"capability": capability, "risk_level": risk},
            actor="kernel",
        )

    # ── Risk lookup ────────────────────────────────────────────────

    def risk_for(self, name: str, kernel: Kernel | None = None, mcp_default_high: bool = False) -> str:
        """Return 'forbidden', 'high', or 'low'.

        External-tool lookups are in-memory and fast. Kernel-backed lookups
        are cached per (capability, mcp_default_high) key and invalidated on
        any policy mutation.
        """
        if name in self._external_forbidden:
            return "forbidden"
        if name in self._external_needs_user:
            return "high"
        if name in self._external_auto_allow:
            return "low"
        cache_key = (name, mcp_default_high)
        cached = self._risk_cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._risk_for_uncached(name, kernel, mcp_default_high)
        self._risk_cache[cache_key] = result
        return result

    def _risk_for_uncached(self, name: str, kernel: Kernel | None, mcp_default_high: bool) -> str:
        if kernel is not None:
            try:
                rows = kernel.query_state("policy_events", capability=name, status="active", limit=1)
                if rows:
                    risk_level = rows[0].get("risk_level", "low")
                    if risk_level == "forbidden":
                        return "forbidden"
                    if risk_level == "high":
                        return "high"
                    return "low"
            except Exception:
                logger.debug("policy_events table may not exist", exc_info=True)
        return "high" if mcp_default_high else "low"

    def is_forbidden(self, name: str, kernel: Kernel | None = None) -> bool:
        return self.risk_for(name, kernel=kernel) == "forbidden"

    # ── External MCP tools ─────────────────────────────────────────

    def register_external_tool(self, name: str, *, risk: str) -> None:
        """Register an external MCP tool policy via event-sourced persistence."""
        self._risk_cache.clear()
        if self._kernel is not None:
            existing_rows = self._kernel.query_state("policy_events", capability=name, limit=1)
            if existing_rows:
                existing = existing_rows[0]
                if existing.get("status") == "revoked":
                    self._kernel.emit_event(
                        "PolicyCreated", "policy", f"policy_{name}",
                        payload={"capability": name, "risk_level": risk},
                        actor="kernel",
                    )
                else:
                    existing_risk = existing.get("risk_level")
                    if existing_risk != risk:
                        self._kernel.emit_event(
                            "PolicyUpdated", "policy", f"policy_{name}",
                            payload={"capability": name, "risk_level": risk},
                            actor="kernel",
                        )
            else:
                self._kernel.emit_event(
                    "PolicyCreated", "policy", f"policy_{name}",
                    payload={"capability": name, "risk_level": risk},
                    actor="kernel",
                )
        self._external_auto_allow.discard(name)
        self._external_needs_user.discard(name)
        self._external_forbidden.discard(name)
        if risk == "forbidden":
            self._external_forbidden.add(name)
        elif risk == "high":
            self._external_needs_user.add(name)
        else:
            self._external_auto_allow.add(name)

    def clear_external_tools(self) -> None:
        """Revoke all external tool policies and clear in-memory cache."""
        self._risk_cache.clear()
        all_names = self._external_auto_allow | self._external_needs_user | self._external_forbidden
        if self._kernel is not None and all_names:
            for name in all_names:
                self._kernel.emit_event(
                    "PolicyRevoked", "policy", f"policy_{name}",
                    payload={"capability": name}, actor="kernel",
                )
        self._external_auto_allow.clear()
        self._external_needs_user.clear()
        self._external_forbidden.clear()

    def all_registered_tools(self, kernel: Kernel | None = None) -> set[str]:
        result: set[str] = self._external_auto_allow | self._external_needs_user | self._external_forbidden
        if kernel is not None:
            rows = kernel.query_state("policy_events", status="active", limit=500)
            for row in rows:
                result.add(row.get("capability", ""))
        return result

    # ── Principal grant check (ex-Gate 2) ─────────────────────────

    @staticmethod
    def _principal_has_grant(principal: Principal, capability: str, kernel: Kernel) -> bool:
        if principal.type in ("system", "user"):
            return True
        try:
            grants = kernel.query_state(
                "grant_events", principal_id=principal.principal_id,
                capability=capability, status="active", limit=1,
            )
            if grants:
                return True
            grants = kernel.query_state(
                "grant_events", principal_id=principal.principal_id,
                capability="*", status="active", limit=1,
            )
            return len(grants) > 0
        except Exception:
            logger.warning(
                "grant_events query failed for agent principal %s (capability=%s) — fail-closed",
                principal.principal_id, capability, exc_info=True,
            )
            return False

    # ── Capability authorization (4-gate model, ex-Gateway) ───────

    @staticmethod
    def _parse_approval_params(approval: dict[str, Any]) -> dict[str, Any]:
        raw = approval.get("params") or "{}"
        if isinstance(raw, str):
            return json.loads(raw)
        return dict(raw)

    @staticmethod
    def _consume_pre_approved(
        kernel: Kernel,
        approval_id: str,
        name: str,
        args: dict[str, Any],
        *,
        actor: str,
        correlation_id: str | None,
    ) -> dict | None:
        """Verify a pending approval matches this invocation; grant or return error."""
        rows = kernel.query_state("approvals", id=approval_id)
        if not rows:
            return {"status": "error", "error": f"Approval not found: {approval_id}"}
        approval = rows[0]
        if approval.get("status") != "pending":
            return {"status": "error", "error": f"Approval not pending: {approval.get('status')}"}
        if approval.get("action") != name:
            return {"status": "error", "error": "Approval action does not match capability"}
        try:
            recorded_args = CapabilityGovernance._parse_approval_params(approval)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "error": "Approval record has invalid params"}
        if recorded_args != args:
            return {"status": "error", "error": "Approval params do not match capability args"}
        kernel.grant_approval(
            approval_id, action=name, actor=actor,
            reason="pre_approved", correlation_id=correlation_id,
        )
        return None

    def decide(
        self,
        principal: Principal,
        capability: str,
        args: dict[str, Any],
        kernel: Kernel,
        *,
        correlation_id: str | None = None,
        pre_approved: bool = False,
        approval_id: str | None = None,
        execution_id: str | None = None,
    ) -> CapabilityDecision:
        """4-gate capability authorization decision."""
        from app.core.harness.mcp_hub import mcp_hub
        from app.core.runtime.sensitive_router import sensitive_router
        from app.core.runtime.taint import is_write_class_tool, taint_registry

        # Gate 1: forbidden by event-sourced policy
        policy_risk = self.risk_for(
            capability, kernel=kernel,
            mcp_default_high=mcp_hub.needs_confirmation(capability),
        )
        if policy_risk == "forbidden":
            return CapabilityDecision("deny", "forbidden_by_policy")

        # Gate 2: principal capability via grant_events
        if principal.type == "agent":
            if not self._principal_has_grant(principal, capability, kernel):
                return CapabilityDecision("deny", "principal_not_authorized")

        # Gate 3: pre-approved fast path
        if pre_approved:
            if not approval_id:
                return CapabilityDecision("deny", "pre_approved_requires_approval_id")
            pre_err = self._consume_pre_approved(
                kernel, approval_id, capability, args,
                actor=principal.actor, correlation_id=correlation_id,
            )
            if pre_err is not None:
                return CapabilityDecision("deny", pre_err.get("error", "pre_approved_mismatch"))

        # Gate 4: risk assessment + approval
        if not pre_approved:
            risk = sensitive_router.elevated_risk(capability, args) or (
                "high" if policy_risk == "high" else "low"
            )
            if (
                correlation_id
                and taint_registry.is_tainted(correlation_id)
                and is_write_class_tool(capability)
            ):
                risk = "high"

            if risk == "high" and principal.type != "user":
                return CapabilityDecision("deny", f"high_risk_{principal.type}_auto_denied")

            approval = kernel.request_approval(
                action=capability, risk=risk, ctx={"args": args},
                actor=principal.actor, correlation_id=correlation_id,
            )
            if approval["status"] != "approved":
                return CapabilityDecision(
                    "defer", approval.get("reason", "needs_user_confirmation"),
                    approval["approval_id"],
                )

        return CapabilityDecision("allow", "approved")

    # ── Approval queries (ex-ApprovalEngine) ──────────────────────

    @staticmethod
    def get_approval(kernel: Kernel, approval_id: str) -> dict | None:
        rows = kernel.query_state("approvals", id=approval_id)
        return rows[0] if rows else None

    @staticmethod
    def list_pending(kernel: Kernel) -> list[dict]:
        return kernel.query_state("approvals", status="pending")

    @staticmethod
    def list_all(kernel: Kernel, limit: int = 50) -> list[dict]:
        return kernel.query_state("approvals", limit=limit)

    @staticmethod
    def list_pending_enriched(kernel: Kernel) -> list[dict]:
        """List pending approvals with context info (correlation_id, conversation title, task info).

        Batched to avoid N+1: one ``read_events`` call fetches all
        ApprovalRequested events, one ``query_state`` call fetches all tasks.
        """
        pending = kernel.query_state("approvals", status="pending")
        if not pending:
            return []

        # Batch 1: all ApprovalRequested events in one query.
        approval_ids = [a["id"] for a in pending]
        correlation_map: dict[str, str] = {}
        for aid in approval_ids:
            events = kernel.read_events(
                aggregate_type="approval", aggregate_id=aid,
                type="ApprovalRequested", limit=1,
            )
            if events:
                correlation_map[aid] = events[0].correlation_id or ""

        # Batch 2: collect unique task ids, single query per unique id
        # (deduplication avoids re-querying the same task across approvals).
        task_ids = {a.get("task_id") for a in pending if a.get("task_id")}
        task_map: dict[str, str] = {}
        for tid in task_ids:
            try:
                task_rows = kernel.query_state("tasks", id=tid)
                if task_rows:
                    task_map[tid] = task_rows[0].get("name", "")
            except Exception:
                pass

        enriched = []
        for a in pending:
            corr_id = correlation_map.get(a["id"], "")
            enriched.append({
                **a,
                "correlation_id": corr_id,
                "flow_type": _classify_flow(corr_id, a.get("task_id"), task_map),
                "flow_label": _label_flow(corr_id, a.get("task_id"), task_map),
            })
        return enriched

    # ── Lifecycle ─────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear in-memory caches — for test isolation."""
        self._external_auto_allow.clear()
        self._external_needs_user.clear()
        self._external_forbidden.clear()
        self._risk_cache.clear()
        self._kernel = None


from app.core.runtime.runtime_container import _LazyProxy, runtime
capability_governance = _LazyProxy(lambda: runtime.capability_governance)

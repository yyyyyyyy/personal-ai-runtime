"""CapabilityGateway — unified capability authorization.

Reads policy_events and grant_events projections (event-sourced) for
authorization decisions. Replaces inline 4-gate model and AgentDefinition.tools.

Gate 2 reads grant_events (Principal → Capability), not
AgentDefinition.tools (persona declaration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .principal import Principal

if TYPE_CHECKING:
    from .kernel.kernel import Kernel


@dataclass(frozen=True)
class CapabilityDecision:
    """Result of a capability authorization check."""

    decision: str  # "allow" | "deny" | "defer"
    reason: str
    approval_id: str | None = None


class CapabilityGateway:
    """Unified capability authorization service.

    Gate 1: policy_events projection (forbidden check)
    Gate 2: grant_events projection (principal authorization)
    Gate 3: pre-approved fast path
    Gate 4: risk assessment + approval

    Fail-closed: agent principals without matching grants are denied.
    """

    def decide(
        self,
        principal: Principal,
        capability: str,
        args: dict[str, Any],
        kernel: "Kernel",
        *,
        correlation_id: str | None = None,
        pre_approved: bool = False,
        approval_id: str | None = None,
        execution_id: str | None = None,
    ) -> CapabilityDecision:
        from app.core.harness.mcp_hub import mcp_hub
        from app.core.runtime.capability_policy import capability_policy
        from app.core.runtime.sensitive_router import sensitive_router
        from app.core.runtime.taint import is_write_class_tool, taint_registry

        # Gate 1: forbidden by event-sourced policy
        policy_risk = capability_policy.risk_for(
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
            pre_err = kernel._consume_pre_approved(
                approval_id,
                capability,
                args,
                actor=principal.actor,
                correlation_id=correlation_id,
            )
            if pre_err is not None:
                return CapabilityDecision(
                    "deny",
                    pre_err.get("error", "pre_approved_mismatch"),
                )

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

            # Non-user principals cannot resolve approvals (no UI).
            # Auto-deny high-risk rather than creating orphan approvals.
            if risk == "high" and principal.type != "user":
                return CapabilityDecision(
                    "deny",
                    f"high_risk_{principal.type}_auto_denied",
                )

            approval = kernel.request_approval(
                action=capability,
                risk=risk,
                ctx={"args": args},
                actor=principal.actor,
                correlation_id=correlation_id,
            )
            if approval["status"] != "approved":
                return CapabilityDecision(
                    "defer",
                    approval.get("reason", "needs_user_confirmation"),
                    approval["approval_id"],
                )

        return CapabilityDecision("allow", "approved")

    def _principal_has_grant(
        self, principal: Principal, capability: str, kernel: "Kernel"
    ) -> bool:
        """Check grant_events projection for principal authorization.

        system + user principals always pass (wildcard grants).
        agent principals must have an active grant.
        On DB failure, fail-closed for agent principals (deny).
        """
        if principal.type in ("system", "user"):
            return True

        try:
            grants = kernel.query_state(
                "grant_events",
                principal_id=principal.principal_id,
                capability=capability,
                status="active",
                limit=1,
            )
            if grants:
                return True

            grants = kernel.query_state(
                "grant_events",
                principal_id=principal.principal_id,
                capability="*",
                status="active",
                limit=1,
            )
            return len(grants) > 0
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "grant_events query failed for agent principal %s (capability=%s) "
                "— fail-closed: denying",
                principal.principal_id, capability, exc_info=True,
            )
            return False


capability_gateway = CapabilityGateway()
# registered in RuntimeContainer.inventory()

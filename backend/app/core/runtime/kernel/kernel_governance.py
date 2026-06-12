"""Kernel Governance Mixin — approval and authorization workflows.

Extracted from kernel.py to keep the main kernel module focused on the
core ABI (emit_event / read_events / query_state).

All approval lifecycle (request → grant/deny → emit ApprovalRequested/
ApprovalGranted/ApprovalDenied events) lives here.
"""

from __future__ import annotations

import uuid
from typing import Any

from ._mixin_protocol import _KernelMixinInterface


class GovernanceMixin(_KernelMixinInterface):
    """Approval governance for capability invocations.

    Mixed into Kernel. Uses self._db, self.emit_event, and related
    kernel-space resources.
    """

    def request_approval(
        self,
        action: str,
        risk: str = "low",
        ctx: dict[str, Any] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
    ) -> dict:
        """Request approval for a capability invocation.

        Risk policy:
          - "low"  → auto_allow, emit ApprovalGranted immediately
          - "high" → needs_user, emit ApprovalRequested and return pending
        """
        approval_id = f"apr_{uuid.uuid4().hex}"

        self.emit_event(
            type="ApprovalRequested",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": action, "risk": risk, "ctx": ctx or {}},
            actor=actor,
            correlation_id=correlation_id,
        )

        if risk == "low":
            self.emit_event(
                type="ApprovalGranted",
                aggregate_type="approval",
                aggregate_id=approval_id,
                payload={"action": action, "reason": "auto_allow"},
                actor="kernel",
                correlation_id=correlation_id,
            )
            return {"status": "approved", "approval_id": approval_id}
        else:
            return {
                "status": "pending",
                "approval_id": approval_id,
                "reason": "needs_user_confirmation",
            }

    def grant_approval(
        self,
        approval_id: str,
        action: str = "",
        actor: str = "user",
        reason: str = "",
        correlation_id: str | None = None,
    ) -> None:
        """Record an approval grant on the governed approval projection."""
        self.emit_event(
            type="ApprovalGranted",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": action, "reason": reason},
            actor=actor,
            correlation_id=correlation_id,
        )

    def deny_approval(
        self,
        approval_id: str,
        action: str = "",
        actor: str = "user",
        reason: str = "",
        correlation_id: str | None = None,
    ) -> None:
        """Record an approval denial on the governed approval projection."""
        self.emit_event(
            type="ApprovalDenied",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": action, "reason": reason},
            actor=actor,
            correlation_id=correlation_id,
        )

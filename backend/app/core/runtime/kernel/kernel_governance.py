"""Kernel Governance Mixin — approval and authorization workflows.

Extracted from kernel.py to keep the main kernel module focused on the
core ABI (emit_event / read_events / query_state).

All approval lifecycle (request → grant/deny → emit ApprovalRequested/
ApprovalGranted/ApprovalDenied events) lives here.

Approval expiry: pending approvals auto-expire after 24h (configurable).
BackgroundWorker periodically calls expire_stale_approvals() to clean up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ._mixin_protocol import _KernelMixinInterface

DEFAULT_APPROVAL_TTL_SECONDS = 86_400  # 24 hours


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
        expires_in_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS,
    ) -> dict:
        """Request approval for a capability invocation.

        Risk policy:
          - "low"  → auto_allow, emit ApprovalGranted immediately
          - "high" → needs_user, emit ApprovalRequested and return pending
        """
        approval_id = f"apr_{uuid.uuid4().hex}"
        expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in_seconds)).isoformat()

        self.emit_event(
            type="ApprovalRequested",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={
                "action": action,
                "risk": risk,
                "ctx": ctx or {},
                "expires_at": expires_at,
            },
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

    def expire_stale_approvals(self) -> int:
        """Expire all pending approvals whose expires_at has passed.

        Returns the count of approvals expired.
        """
        expired_ids: list[str] = []
        with self._db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, action FROM approvals WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            ).fetchall()
            for row in rows:
                expired_ids.append(row["id"])

        for approval_id in expired_ids:
            self.emit_event(
                type="ApprovalExpired",
                aggregate_type="approval",
                aggregate_id=approval_id,
                payload={"action": "", "reason": "auto_expired"},
                actor="kernel",
            )
        return len(expired_ids)

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

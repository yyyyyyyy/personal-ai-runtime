"""Approval Engine — manages approval workflows for write operations.

All writes to the `approvals` projection go through the Kernel.
"""

import uuid

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_instance import kernel
from app.store.database import db


class ApprovalEngine:
    """Manages the approval lifecycle: request → pending → approve/reject."""

    def request_approval(
        self,
        action: str,
        params: dict | None = None,
        task_id: str | None = None,
        proposed_by: str = "system",
    ) -> dict:
        """Create an approval request via Kernel event."""
        approval_id = str(uuid.uuid4())

        kernel.emit_event(
            type="ApprovalRequested",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={
                "action": action,
                "risk": "high",
                "ctx": {"task_id": task_id, "args": params or {}, "proposed_by": proposed_by},
            },
            actor=proposed_by,
        )

        event_bus.publish(EventType.APPROVAL_REQUESTED, {
            "approval_id": approval_id,
            "action": action,
            "params": params,
            "task_id": task_id,
        })

        approval = self.get_approval(approval_id)
        if approval is None:
            raise RuntimeError(f"Approval {approval_id} not found after request")
        return approval

    def approve(self, approval_id: str, resolved_by: str = "user") -> dict | None:
        """Approve a pending approval request."""
        return self._resolve(approval_id, "ApprovalGranted", resolved_by)

    def reject(self, approval_id: str, reason: str = "", resolved_by: str = "user") -> dict | None:
        """Reject a pending approval request."""
        return self._resolve(approval_id, "ApprovalDenied", resolved_by, reason)

    def _resolve(
        self,
        approval_id: str,
        event_type: str,
        resolved_by: str,
        reason: str = "",
    ) -> dict | None:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        if approval["status"] != "pending":
            raise ValueError(f"Approval {approval_id} is already {approval['status']}")

        kernel.emit_event(
            type=event_type,
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": approval.get("action", ""), "reason": reason},
            actor=resolved_by,
        )

        status = "approved" if event_type == "ApprovalGranted" else "denied"
        event_bus.publish(EventType.APPROVAL_RESOLVED, {
            "approval_id": approval_id,
            "status": status,
            "reason": reason,
        })

        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None

    def list_pending(self) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


approval_engine = ApprovalEngine()

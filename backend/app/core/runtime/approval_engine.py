"""Approval Engine — manages approval workflows for write operations.

All writes to the `approvals` projection go through the Kernel.
"""

from app.core.runtime.kernel_instance import kernel


class ApprovalEngine:
    """Manages the approval lifecycle: request → pending → approve/reject."""

    def request_approval(
        self,
        action: str,
        params: dict | None = None,
        task_id: str | None = None,
        proposed_by: str = "system",
    ) -> dict:
        """Create an approval request via Kernel governance ABI."""
        result = kernel.request_approval(
            action=action,
            risk="high",
            ctx={"task_id": task_id, "args": params or {}, "proposed_by": proposed_by},
            actor=proposed_by,
        )
        approval_id = result["approval_id"]

        approval = self.get_approval(approval_id)
        if approval is None:
            raise RuntimeError(f"Approval {approval_id} not found after request")
        return approval

    def approve(self, approval_id: str, resolved_by: str = "user") -> dict | None:
        """Approve a pending approval request."""
        return self._resolve(approval_id, granted=True, resolved_by=resolved_by)

    def reject(self, approval_id: str, reason: str = "", resolved_by: str = "user") -> dict | None:
        """Reject a pending approval request."""
        return self._resolve(approval_id, granted=False, resolved_by=resolved_by, reason=reason)

    def _resolve(
        self,
        approval_id: str,
        granted: bool,
        resolved_by: str,
        reason: str = "",
    ) -> dict | None:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        if approval["status"] != "pending":
            raise ValueError(f"Approval {approval_id} is already {approval['status']}")

        action = approval.get("action", "")
        if granted:
            kernel.grant_approval(approval_id, action=action, actor=resolved_by, reason=reason)
        else:
            kernel.deny_approval(approval_id, action=action, actor=resolved_by, reason=reason)

        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict | None:
        rows = kernel.query_state("approvals", id=approval_id)
        return rows[0] if rows else None

    def list_pending(self) -> list[dict]:
        return kernel.query_state("approvals", status="pending")

    def list_all(self, limit: int = 50) -> list[dict]:
        return kernel.query_state("approvals", limit=limit)


approval_engine = ApprovalEngine()

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

    def list_pending_enriched(self) -> list[dict]:
        """List pending approvals with context info (correlation_id, conversation title, task info).

        Enriches each approval record with:
          - flow_type: "对话" (chat), "任务" (task), "定时任务" (scheduled), or "未知"
          - flow_label: human-readable label for the source (conversation title, task name, etc.)
          - correlation_id: the correlation identifier from event_log
        """
        pending = self.list_pending()
        if not pending:
            return []

        approval_ids = [a["id"] for a in pending]

        # Query event_log via Kernel API for ApprovalRequested events to get correlation_id
        correlation_map: dict[str, str] = {}
        for aid in approval_ids:
            events = kernel.read_events(
                aggregate_type="approval",
                aggregate_id=aid,
                type="ApprovalRequested",
                limit=1,
            )
            if events:
                correlation_map[aid] = events[0].correlation_id or ""

        # Build task lookup via kernel.query_state
        task_map: dict[str, str] = {}
        for a in pending:
            tid = a.get("task_id")
            if tid:
                try:
                    task_rows = kernel.query_state("tasks", id=tid)
                    if task_rows:
                        task_map[tid] = task_rows[0].get("name", "")
                except Exception:
                    pass

        # Enrich each approval
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


# ── Flow classification helpers ───────────────────────────────────────

# Registry-based matching: avoids treating correlation_id naming
# conventions as a type system.
_CORR_PREFIX_MAP: list[tuple[str, str]] = [
    ("chat_", "对话"),
    ("sched_", "定时任务"),
    ("trigger_", "定时任务"),
]
_CORR_EXACT_MAP: dict[str, tuple[str, str]] = {
    "approval-resolve-test": ("测试", "审批解析测试"),
}


def _classify_flow(
    corr_id: str,
    task_id: str | None,
    task_map: dict[str, str],
) -> str:
    if task_id and task_id in task_map:
        return "任务"
    for prefix, label in _CORR_PREFIX_MAP:
        if corr_id.startswith(prefix):
            return label
    exact = _CORR_EXACT_MAP.get(corr_id)
    if exact:
        return exact[0]
    return "系统" if corr_id else "未知"


def _label_flow(
    corr_id: str,
    task_id: str | None,
    task_map: dict[str, str],
) -> str:
    if task_id and task_id in task_map:
        return task_map[task_id]
    for prefix, label in _CORR_PREFIX_MAP:
        if corr_id.startswith(prefix):
            return f"{label} ({corr_id})"
    exact = _CORR_EXACT_MAP.get(corr_id)
    if exact:
        return exact[1]
    return corr_id or ""


approval_engine = ApprovalEngine()

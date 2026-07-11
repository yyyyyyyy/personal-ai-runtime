"""Approvals API — manage approval workflows with flow context."""

import json

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.runtime import read_ports
from app.core.runtime.capability_governance import capability_governance
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["approvals"])

# ── Flow classification helpers (v0.11.0: moved from capability_governance) ──
# These are UI-presentation concerns — Chinese labels for the approval list.
# They do NOT belong in the governance layer which should remain pure decision logic.

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


def _list_pending_enriched(kernel) -> list[dict]:
    """List pending approvals with flow context enriched from event_log.

    Moved from capability_governance.list_pending_enriched (v0.11.0) —
    this is a UI-presentation concern, not a governance decision.
    """
    pending = read_ports.query_pending_approvals()
    if not pending:
        return []

    approval_ids = [a["id"] for a in pending]
    correlation_map: dict[str, str] = {}
    for aid in approval_ids:
        events = kernel.read_events(
            aggregate_type="approval", aggregate_id=aid,
            type="ApprovalRequested", limit=1,
        )
        if events:
            correlation_map[aid] = events[0].correlation_id or ""

    task_ids = {str(a["task_id"]) for a in pending if a.get("task_id")}
    task_map: dict[str, str] = {}
    for tid in task_ids:
        try:
            item = read_ports.query_work_item(tid)
            if item:
                task_map[tid] = item.get("title", "")
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


@router.get("/")
async def list_approvals(limit: int = 50, pending_only: bool = False, enriched: bool = False):
    """List approvals, optionally enriched with flow context.

    When enriched=true, each approval includes:
      - flow_type: "对话" | "任务" | "定时任务" | "测试" | "系统" | "未知"
      - flow_label: human-readable source label
      - correlation_id: event correlation identifier
    """
    if pending_only and enriched:
        return _list_pending_enriched(kernel)
    if pending_only:
        return capability_governance.list_pending(kernel)
    return capability_governance.list_all(kernel, limit=limit)


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    """Get a single approval by ID."""
    approval = capability_governance.get_approval(kernel, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/approve")
async def approve(approval_id: str):
    """Approve an approval and execute the authorized capability.

    Goes through the same submit_command → ApproveRequested handler pipeline
    as the chat resolve endpoint.  When the approval was created from a chat
    context, the conversation is automatically resumed; otherwise the
    capability is still executed but no conversation reply is sent.
    """
    from app.core.runtime.agent_scheduler import ensure_scheduler, get_scheduler

    approval = capability_governance.get_approval(kernel, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Approval is already {approval.get('status')}")

    tool_name = approval.get("action", "")
    try:
        raw = approval.get("params", "{}")
        tool_args = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Approval has invalid params")

    # Try to find conversation_id from the approval's correlation chain
    conv_id = ""
    events = kernel.read_events(
        aggregate_type="approval",
        aggregate_id=approval_id,
        type="ApprovalRequested",
        limit=1,
    )
    if events and events[0].correlation_id:
        corr_id = events[0].correlation_id
        if corr_id.startswith("chat"):
            # Look up the conversation from recent messages
            chat_events = kernel.read_events(
                aggregate_type="conversation",
                correlation_id=corr_id,
                types=["MessageAppended"],
                limit=1,
            )
            if chat_events:
                conv_id = chat_events[0].aggregate_id

    await ensure_scheduler(kernel)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    result = await kernel.submit_command(
        "ApproveRequested",
        "approval",
        f"approve_{approval_id}",
        payload={
            "approval_id": approval_id,
            "decision": "approve",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "conv_id": conv_id,
            "tool_call_id": "",
        },
        actor="user",
        timeout=settings.submit_command_timeout_approval,
    )

    if result.get("error") == "timeout":
        raise HTTPException(status_code=504, detail="Approval resolution timed out")

    return {"status": result.get("status", "error"), "result": result.get("result", "")}


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, reason: str = ""):
    """Reject a pending approval through the standard handler pipeline."""
    from app.core.runtime.agent_scheduler import ensure_scheduler, get_scheduler

    approval = capability_governance.get_approval(kernel, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Approval is already {approval.get('status')}")

    await ensure_scheduler(kernel)
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    result = await kernel.submit_command(
        "ApproveRequested",
        "approval",
        f"approve_{approval_id}",
        payload={
            "approval_id": approval_id,
            "decision": "deny",
            "tool_name": approval.get("action", ""),
            "tool_args": {},
            "conv_id": "",
            "tool_call_id": "",
        },
        actor="user",
        timeout=settings.submit_command_timeout_approval,
    )

    if result.get("error") == "timeout":
        raise HTTPException(status_code=504, detail="Approval resolution timed out")

    return {"status": result.get("status", "denied")}

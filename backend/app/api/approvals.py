"""Approvals API — manage approval workflows with flow context."""

from fastapi import APIRouter, HTTPException

from app.core.runtime.approval_engine import approval_engine

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/")
async def list_approvals(limit: int = 50, pending_only: bool = False, enriched: bool = False):
    """List approvals, optionally enriched with flow context.

    When enriched=true, each approval includes:
      - flow_type: "对话" | "任务" | "定时任务" | "测试" | "系统" | "未知"
      - flow_label: human-readable source label
      - correlation_id: event correlation identifier
    """
    if pending_only and enriched:
        return approval_engine.list_pending_enriched()
    if pending_only:
        return approval_engine.list_pending()
    return approval_engine.list_all(limit=limit)


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    """Get a single approval by ID."""
    approval = approval_engine.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/approve")
async def approve(approval_id: str):
    """Mark approval as approved in projection only.

    For chat tool execution, use POST /api/chat/approvals/{id}/resolve instead.
    This endpoint does not invoke the capability or resume the conversation.
    """
    result = approval_engine.approve(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, reason: str = ""):
    """Reject an approval. Does not resume the conversation."""
    result = approval_engine.reject(approval_id, reason=reason)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result

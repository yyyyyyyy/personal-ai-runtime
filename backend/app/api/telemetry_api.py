"""Telemetry API — cost, token usage, tool stats, memory stats, and system health."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.core.runtime.kernel_instance import kernel
from app.core.telemetry.telemetry import telemetry

router = APIRouter(tags=["telemetry"])


@router.get("/cost/summary")
async def cost_summary(days: int = Query(default=7, ge=1, le=90)):
    """Get LLM cost/token/latency summary."""
    return telemetry.get_llm_summary(days=days)


@router.get("/cost/by-model")
async def cost_by_model(days: int = Query(default=7, ge=1, le=90)):
    """Get LLM token/cost breakdown per provider and model."""
    return telemetry.get_llm_summary_by_model(days=days)


@router.get("/llm-calls")
async def list_llm_calls(limit: int = 50, offset: int = 0):
    """List recent LLM calls."""
    return telemetry.get_llm_calls(limit=limit, offset=offset)


@router.get("/tool-calls")
async def list_tool_calls(limit: int = 50, tool_name: str | None = None):
    """List recent tool calls, optionally filtered by tool name."""
    return telemetry.get_tool_calls(limit=limit, tool_name=tool_name)


@router.get("/tool-summary")
async def tool_summary(days: int = Query(default=7, ge=1, le=90)):
    """Get tool call success rates and latencies."""
    return telemetry.get_tool_summary(days=days)


@router.get("/memory/stats")
async def memory_stats():
    """Get memory system stats: total count, categories, recent additions."""
    return telemetry.get_memory_stats()


@router.get("/health")
async def health_snapshot():
    """Get runtime health snapshot: queue length, failure rates."""
    return telemetry.get_health()


@router.get("/memory-index-repairs")
async def memory_index_repairs(status: str = Query(default="all")):
    """List memory index repair queue rows and aggregate counts."""
    return telemetry.get_memory_index_repairs(status=status)


@router.post("/memory-index-repairs/{repair_id}/retry")
async def retry_memory_index_repair(repair_id: int):
    """Reset a failed_permanent repair row for another drain attempt."""
    result = telemetry.retry_memory_index_repair(repair_id)
    if not result.get("ok"):
        from fastapi import HTTPException

        if result.get("error") == "not_found":
            raise HTTPException(status_code=404, detail="Repair row not found")
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/governance")
async def governance_summary(days: int = Query(default=7, ge=1, le=90)):
    """Aggregate capability governance activity for the Trust Report UI.

    Surfaces counts of: tools invoked, tools denied (high-risk blocked),
    tools deferred to user approval, approvals approved/rejected/expired,
    and taint-elevated decisions — all within the window.

    This makes the 3-gate governance model visible: users can see exactly
    how many risky operations the LLM attempted and how many were caught.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    invoked = kernel.read_events(type="CapabilityInvoked", since_ts=since, limit=1000)
    denied = kernel.read_events(type="CapabilityDenied", since_ts=since, limit=1000)
    deferred = kernel.read_events(type="CapabilityDeferred", since_ts=since, limit=1000)
    approve_req = kernel.read_events(type="ApproveRequested", since_ts=since, limit=1000)
    approve_done = kernel.read_events(type="ApproveCompleted", since_ts=since, limit=1000)

    # Tool-name breakdown of invoked capabilities
    by_tool: dict[str, int] = {}
    taint_elevated = 0
    for evt in invoked:
        name = str(evt.payload.get("name", "unknown"))
        by_tool[name] = by_tool.get(name, 0) + 1
        if evt.payload.get("taint_elevated"):
            taint_elevated += 1

    denied_tools: dict[str, int] = {}
    for evt in denied:
        name = str(evt.payload.get("name", "unknown"))
        denied_tools[name] = denied_tools.get(name, 0) + 1

    approved_count = sum(
        1 for e in approve_done
        if e.payload.get("decision") == "approved"
    )
    rejected_count = sum(
        1 for e in approve_done
        if e.payload.get("decision") == "rejected"
    )
    expired_count = sum(
        1 for e in approve_done
        if e.payload.get("decision") not in ("approved", "rejected")
    )

    return {
        "window_days": days,
        "tools_invoked": len(invoked),
        "tools_denied": len(denied),
        "tools_deferred": len(deferred),
        "approvals_requested": len(approve_req),
        "approvals_approved": approved_count,
        "approvals_rejected": rejected_count,
        "approvals_expired": expired_count,
        "taint_elevated": taint_elevated,
        "by_tool": by_tool,
        "denied_tools": denied_tools,
    }

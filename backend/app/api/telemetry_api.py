"""Telemetry API — cost, token usage, tool stats, memory stats, and system health."""

from fastapi import APIRouter, Query

from app.core.telemetry.telemetry import telemetry

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/cost/summary")
async def cost_summary(days: int = Query(default=7, ge=1, le=90)):
    """Get LLM cost/token/latency summary."""
    return telemetry.get_llm_summary(days=days)


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

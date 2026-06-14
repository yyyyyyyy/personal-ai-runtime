"""Events API — query the governed event log."""

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.legacy_event_adapter import goal_legacy_events, recent_legacy_events

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/")
async def list_events(days: int = Query(default=7, ge=1), limit: int = Query(default=50, ge=1, le=500), type: str | None = Query(default=None), goal_id: str | None = None):
    """List events with optional filters."""
    if goal_id:
        return goal_legacy_events(goal_id, limit=limit)
    return recent_legacy_events(kernel.read_events, days=days, limit=limit, event_type=type)

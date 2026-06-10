"""Events API — query the governed event log."""

from fastapi import APIRouter

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.legacy_event_adapter import goal_legacy_events, recent_legacy_events

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/")
async def list_events(days: int = 7, limit: int = 50, type: str | None = None, goal_id: str | None = None):
    """List events with optional filters."""
    if goal_id:
        return goal_legacy_events(goal_id, limit=limit)
    return recent_legacy_events(kernel.read_events, days=days, limit=limit, event_type=type)

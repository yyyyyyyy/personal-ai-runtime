"""Events API — query the event log."""

from fastapi import APIRouter
from app.core.event_recorder import event_recorder

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/")
async def list_events(days: int = 7, limit: int = 50, type: str | None = None, goal_id: str | None = None):
    """List events with optional filters."""
    if type:
        return event_recorder.get_events_by_type(type, limit=limit)
    if goal_id:
        return event_recorder.get_events_for_goal(goal_id, limit=limit)
    return event_recorder.get_recent_events(days=days, limit=limit)

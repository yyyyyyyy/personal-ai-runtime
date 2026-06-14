"""Goals & Actions API — manage goals and their sub-actions."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.legacy_event_adapter import goal_legacy_events

router = APIRouter(prefix="/api/goals", tags=["goals"])

VALID_GOAL_STATUSES = frozenset({"active", "completed", "paused"})


def _validate_score_field(name: str, value: object) -> float:
    if not isinstance(value, (int, float, str)):
        raise HTTPException(status_code=400, detail=f"{name} must be a number")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be a number") from exc
    if not (0.0 <= score <= 1.0):
        raise HTTPException(status_code=400, detail=f"{name} must be between 0.0 and 1.0")
    return score


def _validate_goal_update_fields(body: dict) -> None:
    if "importance" in body:
        body["importance"] = _validate_score_field("importance", body["importance"])
    if "urgency" in body:
        body["urgency"] = _validate_score_field("urgency", body["urgency"])
    if "status" in body and body["status"] not in VALID_GOAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(VALID_GOAL_STATUSES))}",
        )


# --- Goal CRUD ---------------------------------------------------------------

@router.post("/")
async def create_goal(body: dict):
    """Create a new goal."""
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    goal_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    description = body.get("description", "")
    importance = _validate_score_field("importance", body.get("importance", 0.5))
    urgency = _validate_score_field("urgency", body.get("urgency", 0.5))

    deadline = body.get("deadline")
    parent_id = body.get("parent_id")

    kernel.emit_event(
        type="GoalCreated",
        aggregate_type="goal",
        aggregate_id=goal_id,
        payload={
            "title": title,
            "description": description,
            "importance": importance,
            "urgency": urgency,
            "deadline": deadline,
            "parent_id": parent_id,
            "created_at": now,
        },
        actor="user",
    )

    return _get_goal(goal_id)


@router.get("/")
async def list_goals(status: str | None = None, limit: int = 50):
    """List all goals, optionally filtered by status."""
    filters: dict[str, object] = {"limit": limit}
    if status:
        filters["status"] = status
    return kernel.query_state("goals", **filters)


@router.get("/priorities/sorted")
async def get_prioritized_goals():
    """Get goals sorted by priority (importance x urgency x stagnation_time)."""
    goals = kernel.query_state("goals", status="active", limit=500)
    scored = [{**g, "priority_score": _goal_priority_score(g)} for g in goals]
    scored.sort(key=lambda g: g["priority_score"], reverse=True)
    return scored[:20]


@router.get("/stagnant")
async def get_stagnant_goals(days: int = Query(3, ge=1)):
    """Get goals that haven't been updated in the specified number of days."""
    result = kernel.query_state(
        "goals",
        status="active",
        last_activity_older_than_days=days,
        order="last_activity_asc",
        limit=500,
    )
    return result if result else []


@router.get("/{goal_id}")
async def get_goal(goal_id: str):
    """Get a goal with its actions and events."""
    goals = kernel.query_state("goals", id=goal_id)
    if not goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal = goals[0]
    goal["actions"] = kernel.query_state("actions", goal_id=goal_id)
    goal["events"] = goal_legacy_events(goal_id, limit=10)
    return goal


@router.put("/{goal_id}")
@router.patch("/{goal_id}")
async def update_goal(goal_id: str, body: dict):
    """Update a goal's fields (supports PUT and PATCH)."""
    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    updatable = ["title", "description", "status", "progress", "importance", "urgency", "deadline", "parent_id"]
    changed = {}
    for key in updatable:
        if key in body:
            changed[key] = body[key]

    if not changed:
        return goal

    _validate_goal_update_fields(changed)

    if changed.get("status") == "completed":
        kernel.emit_event(
            type="GoalCompleted",
            aggregate_type="goal",
            aggregate_id=goal_id,
            payload=changed,
            actor="user",
        )
    else:
        kernel.emit_event(
            type="GoalUpdated",
            aggregate_type="goal",
            aggregate_id=goal_id,
            payload=changed,
            actor="user",
        )

    return _get_goal(goal_id)


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str):
    """Delete a goal and its sub-actions."""
    if not _get_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")

    for action in kernel.query_state("actions", goal_id=goal_id):
        kernel.emit_event(
            type="ActionDeleted",
            aggregate_type="action",
            aggregate_id=action["id"],
            actor="user",
        )
    kernel.emit_event(
        type="GoalDeleted",
        aggregate_type="goal",
        aggregate_id=goal_id,
        actor="user",
    )
    return {"status": "ok"}


# --- Actions CRUD (event-sourced via Kernel) ---------------------------------

@router.post("/{goal_id}/actions")
async def create_action(goal_id: str, body: dict):
    """Create an action for a goal."""
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    action_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    kernel.emit_event(
        type="ActionCreated",
        aggregate_type="action",
        aggregate_id=action_id,
        payload={
            "goal_id": goal_id,
            "title": title,
            "status": "pending",
            "created_at": now,
        },
        actor="user",
    )
    kernel.emit_event("GoalTouched", "goal", goal_id, actor="user")

    actions = kernel.query_state("actions", id=action_id)
    return actions[0] if actions else {"id": action_id, "goal_id": goal_id, "title": title, "status": "pending"}


@router.put("/{goal_id}/actions/{action_id}")
async def update_action(goal_id: str, action_id: str, body: dict):
    """Update an action's status or title."""
    # Verify action exists
    actions = kernel.query_state("actions", id=action_id)
    if not actions:
        raise HTTPException(status_code=404, detail="Action not found")

    status = body.get("status")
    title = body.get("title")
    payload: dict = {}

    if status:
        payload["status"] = status
        if status == "completed":
            payload["completed_at"] = datetime.now(UTC).isoformat()

    if title:
        payload["title"] = title

    if payload:
        kernel.emit_event(
            type="ActionUpdated",
            aggregate_type="action",
            aggregate_id=action_id,
            payload=payload,
            actor="user",
        )
        kernel.emit_event("GoalTouched", "goal", goal_id, actor="user")

    return {"status": "ok"}


@router.delete("/{goal_id}/actions/{action_id}")
async def delete_action(goal_id: str, action_id: str):
    """Delete an action."""
    # Verify action exists
    actions = kernel.query_state("actions", id=action_id)
    if not actions:
        raise HTTPException(status_code=404, detail="Action not found")

    kernel.emit_event(
        type="ActionDeleted",
        aggregate_type="action",
        aggregate_id=action_id,
        actor="user",
    )
    return {"status": "ok"}


# --- Priority & Stagnation (read-only queries) -------------------------------

def _goal_priority_score(goal: dict) -> float:
    """Match legacy SQL: importance * urgency * days since last activity."""
    from datetime import datetime

    importance = float(goal.get("importance") or 0)
    urgency = float(goal.get("urgency") or 0)
    activity_at = goal.get("last_activity_at") or goal.get("created_at")
    if not activity_at:
        return 0.0
    try:
        activity_dt = datetime.fromisoformat(activity_at)
    except ValueError:
        return importance * urgency
    days_stale = max((datetime.now(UTC) - activity_dt).total_seconds() / 86400.0, 0.0)
    return importance * urgency * days_stale


def _get_goal(goal_id: str) -> dict | None:
    goals = kernel.query_state("goals", id=goal_id)
    return goals[0] if goals else None

"""Goals & Actions API — manage goals and their sub-actions."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.store.database import db
from app.core.event_recorder import event_recorder, Event

router = APIRouter(prefix="/api/goals", tags=["goals"])


# --- Goal CRUD ---

@router.post("/")
async def create_goal(body: dict):
    """Create a new goal."""
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    goal_id = str(uuid.uuid4())
    now = datetime.utcnow()

    description = body.get("description", "")
    importance = float(body.get("importance", 0.5))
    urgency = float(body.get("urgency", 0.5))
    deadline = body.get("deadline")
    parent_id = body.get("parent_id")

    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO goals (id, title, description, status, importance, urgency, deadline, 
               parent_id, created_at, updated_at, last_activity_at)
               VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)""",
            (goal_id, title, description, importance, urgency, deadline, parent_id,
             now.isoformat(), now.isoformat(), now.isoformat()),
        )

    event_recorder.record(Event(
        type="goal_created",
        summary=f"Goal created: {title}",
        goal_id=goal_id,
        payload={"title": title, "importance": importance, "urgency": urgency},
    ))

    return _get_goal(goal_id)


@router.get("/")
async def list_goals(status: str | None = None, limit: int = 50):
    """List all goals, optionally filtered by status."""
    with db.get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM goals ORDER BY importance DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{goal_id}")
async def get_goal(goal_id: str):
    """Get a goal with its actions and events."""
    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Get sub-actions
    with db.get_db() as conn:
        actions = conn.execute(
            "SELECT * FROM actions WHERE goal_id = ? ORDER BY created_at ASC",
            (goal_id,),
        ).fetchall()
    goal["actions"] = [dict(a) for a in actions]

    # Get related events
    events = event_recorder.get_events_for_goal(goal_id, limit=10)
    goal["events"] = events

    return goal


@router.put("/{goal_id}")
async def update_goal(goal_id: str, body: dict):
    """Update a goal's fields."""
    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    updatable = ["title", "description", "status", "progress", "importance", "urgency", "deadline", "parent_id"]
    fields = []
    params = []

    for key in updatable:
        if key in body:
            fields.append(f"{key} = ?")
            params.append(body[key])

    if not fields:
        return goal

    fields.append("updated_at = ?")
    fields.append("last_activity_at = ?")
    now = datetime.utcnow().isoformat()
    params.extend([now, now, goal_id])

    with db.get_db() as conn:
        conn.execute(
            f"UPDATE goals SET {', '.join(fields)} WHERE id = ?",
            params,
        )

    if "status" in body:
        event_recorder.record(Event(
            type="goal_status_changed",
            summary=f"Goal '{goal['title']}' status -> {body['status']}",
            goal_id=goal_id,
        ))

    return _get_goal(goal_id)


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str):
    """Delete a goal and its sub-actions."""
    with db.get_db() as conn:
        conn.execute("DELETE FROM actions WHERE goal_id = ?", (goal_id,))
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return {"status": "ok"}


# --- Actions CRUD ---

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
    now = datetime.utcnow().isoformat()

    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO actions (id, goal_id, title, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (action_id, goal_id, title, now),
        )
        conn.execute(
            "UPDATE goals SET last_activity_at = ?, updated_at = ? WHERE id = ?",
            (now, now, goal_id),
        )

    event_recorder.record(Event(
        type="action_created",
        summary=f"Action created: {title}",
        goal_id=goal_id,
    ))

    return {"id": action_id, "goal_id": goal_id, "title": title, "status": "pending"}


@router.put("/{goal_id}/actions/{action_id}")
async def update_action(goal_id: str, action_id: str, body: dict):
    """Update an action's status or title."""
    status = body.get("status")
    title = body.get("title")

    now = datetime.utcnow().isoformat()
    if status:
        completed_at = now if status == "completed" else None
        with db.get_db() as conn:
            conn.execute(
                "UPDATE actions SET status = ?, completed_at = ? WHERE id = ? AND goal_id = ?",
                (status, completed_at, action_id, goal_id),
            )
            conn.execute(
                "UPDATE goals SET last_activity_at = ?, updated_at = ? WHERE id = ?",
                (now, now, goal_id),
            )

        event_recorder.record(Event(
            type="action_status_changed",
            summary=f"Action status -> {status}",
            goal_id=goal_id,
        ))

    if title:
        with db.get_db() as conn:
            conn.execute(
                "UPDATE actions SET title = ? WHERE id = ? AND goal_id = ?",
                (title, action_id, goal_id),
            )

    return {"status": "ok"}


@router.delete("/{goal_id}/actions/{action_id}")
async def delete_action(goal_id: str, action_id: str):
    """Delete an action."""
    with db.get_db() as conn:
        conn.execute("DELETE FROM actions WHERE id = ? AND goal_id = ?", (action_id, goal_id))
    return {"status": "ok"}


# --- Priority & Stagnation ---

@router.get("/priorities/sorted")
async def get_prioritized_goals():
    """Get goals sorted by priority (importance x urgency x stagnation_time)."""
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT *, 
               (importance * urgency * (julianday('now') - julianday(COALESCE(last_activity_at, created_at)))) as priority_score
               FROM goals WHERE status = 'active' 
               ORDER BY priority_score DESC LIMIT 20"""
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/stagnant")
async def get_stagnant_goals(days: int = 3):
    """Get goals that haven't been updated in the specified number of days."""
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM goals 
               WHERE status = 'active' 
               AND last_activity_at < datetime('now', ?) 
               ORDER BY last_activity_at ASC""",
            (f"-{days} days",),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_goal(goal_id: str) -> dict | None:
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return dict(row) if row else None

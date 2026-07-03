"""Goals & Actions API — manage goals and their sub-actions."""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.models import CreateActionRequest, CreateGoalRequest
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.event_formatting import goal_events

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
async def create_goal(body: CreateGoalRequest):
    """Create a new goal."""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    goal_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    description = body.description
    importance = body.importance
    urgency = body.urgency

    deadline = body.deadline
    parent_id = body.parent_id

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


@router.get("/{goal_id}")
async def get_goal(goal_id: str):
    """Get a goal with its actions and events."""
    goals = kernel.query_state("goals", id=goal_id)
    if not goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal = goals[0]
    goal["actions"] = kernel.query_state("actions", goal_id=goal_id)
    goal["events"] = goal_events(goal_id, limit=10)
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

    # Delete all sub-items via WorkItemDeleted
    for item in kernel.query_state("work_items", parent_goal_id=goal_id):
        kernel.emit_event(
            type="WorkItemDeleted",
            aggregate_type="work_item",
            aggregate_id=item["id"],
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
async def create_action(goal_id: str, body: CreateActionRequest):
    """Create an action for a goal."""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    action_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    kernel.emit_event(
        type="WorkItemCreated",
        aggregate_type="work_item",
        aggregate_id=action_id,
        payload={
            "title": title,
            "work_type": "action",
            "parent_goal_id": goal_id,
            "status": "pending",
            "created_at": now,
        },
        actor="user",
    )
    kernel.emit_event("GoalTouched", "goal", goal_id, actor="user")

    rows = kernel.query_state("work_items", id=action_id)
    return rows[0] if rows else {"id": action_id, "parent_goal_id": goal_id, "title": title, "status": "pending"}


@router.put("/{goal_id}/actions/{action_id}")
async def update_action(goal_id: str, action_id: str, body: dict):
    """Update an action's status or title."""
    rows = kernel.query_state("work_items", id=action_id)
    if not rows:
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
            type="WorkItemUpdated",
            aggregate_type="work_item",
            aggregate_id=action_id,
            payload=payload,
            actor="user",
        )
        kernel.emit_event("GoalTouched", "goal", goal_id, actor="user")

        if status == "completed":
            _on_action_completed(goal_id, action_id, rows[0].get("title", ""))

    return {"status": "ok"}


@router.delete("/{goal_id}/actions/{action_id}")
async def delete_action(goal_id: str, action_id: str):
    """Delete an action."""
    rows = kernel.query_state("work_items", id=action_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Action not found")

    kernel.emit_event(
        type="WorkItemDeleted",
        aggregate_type="work_item",
        aggregate_id=action_id,
        actor="user",
    )
    return {"status": "ok"}


def _get_goal(goal_id: str) -> dict | None:
    goals = kernel.query_state("goals", id=goal_id)
    return goals[0] if goals else None


# --- AI Goal Decomposition ---------------------------------------------------

@router.post("/{goal_id}/decompose")
async def decompose_goal(goal_id: str):
    """Use AI to decompose a goal into actionable steps.

    Returns a list of suggested action titles. The frontend can then
    display these for user confirmation before creating them.
    """
    goal = _get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    title = goal.get("title", "")
    description = goal.get("description", "")

    # Build prompt for goal decomposition
    prompt = f"""You are a goal decomposition assistant. Break down the following goal into 3-7 concrete, actionable steps.

Goal: {title}
{f'Description: {description}' if description else ''}

Return your response as a JSON array of strings, where each string is an action step title.
Example: ["Step 1 title", "Step 2 title", "Step 3 title"]

Only return the JSON array, no other text."""

    try:
        from app.core.agents.llm_failover import llm_router

        client, provider = llm_router.get_client()

        response = await client.chat.completions.create(
            model=provider.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that breaks down goals into actionable steps. Always respond with valid JSON arrays only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )

        content = response.choices[0].message.content or ""

        # Try to parse JSON from the response
        # Handle cases where LLM wraps JSON in markdown code blocks
        content = content.strip()
        if content.startswith("```"):
            # Remove markdown code blocks
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        # Parse the JSON array
        steps = json.loads(content)

        if not isinstance(steps, list):
            raise ValueError("Response is not a list")

        # Validate and limit step titles
        validated_steps = []
        for step in steps[:10]:  # Limit to 10 steps max
            if isinstance(step, str) and step.strip():
                validated_steps.append(step.strip()[:200])  # Limit length

        return {"steps": validated_steps}

    except json.JSONDecodeError:
        # If JSON parsing fails, try to extract steps from plain text
        # Split by newlines or numbered lists
        lines = content.strip().split("\n")
        steps = []
        for line in lines:
            line = line.strip()
            # Remove common list prefixes like "1.", "-", "*"
            if line.startswith(("-", "*")):
                line = line[1:].strip()
            elif "." in line and line[0].isdigit():
                line = line.split(".", 1)[1].strip()
            if line:
                steps.append(line[:200])
        return {"steps": steps[:10]}

    except Exception:
        raise HTTPException(status_code=500, detail="AI decomposition service temporarily unavailable")


def _on_action_completed(goal_id: str, action_id: str, action_title: str):
    """联动逻辑：行动完成时自动更新目标进度、发通知、提炼记忆。"""
    try:
        # 1. 计算目标进度（已完成 action 数 / 总 action 数）
        all_items = kernel.query_state("work_items", parent_goal_id=goal_id, limit=500)
        if all_items:
            completed = sum(1 for a in all_items if a.get("status") == "completed")
            progress = completed / len(all_items)
            kernel.emit_event(
                "GoalUpdated",
                "goal",
                goal_id,
                payload={"progress": progress},
                actor="system",
            )

        # 2. 发通知
        from app.product.notifications import create_notification
        goal_rows = kernel.query_state("goals", id=goal_id)
        goal_title = goal_rows[0]["title"] if goal_rows else "目标"
        all_done = all(a.get("status") == "completed" for a in all_items) if all_items else False
        if all_done and all_items:
            create_notification(
                "goal_complete",
                f"目标「{goal_title}」的所有步骤已完成",
                f"你完成了所有行动步骤：{goal_title}。可以去目标页标记完成，或让 AI 帮你总结经验。",
            )
        else:
            create_notification(
                "goal_progress",
                f"完成一步：{action_title}",
                f"目标「{goal_title}」进度：{completed}/{len(all_actions)} 步已完成。",
            )

        # 3. 提炼经验存入记忆
        from app.core.agents.memory_engine import memory_engine
        memory_engine.store_memory(
            category="event",
            content=f"完成了行动步骤：{action_title}（目标：{goal_title}）",
            source=f"action:{action_id}",
            actor="system",
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to store audited action memory for action_id=%s", action_id,
            exc_info=True,
        )

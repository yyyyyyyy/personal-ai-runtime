"""Work Items API — unified endpoint for tasks, actions, goals (v1.0).

Replaces the type-specific /api/tasks and /api/goals endpoints with a single
router that operates on the work_items projection. Work type discrimination
happens via the `work_type` query parameter or payload field.

v1.0 Phase 3a: this endpoint coexists with /api/goals and /api/tasks. Frontend
migration is incremental; Phase 4 will retire the legacy endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.runtime.task_engine import (
    create_work_item as _create_work_item,
    delete_work_item as _delete_work_item,
    get_sub_work_items as _get_sub_work_items,
    get_work_item as _get_work_item,
    list_work_items as _list_work_items,
    update_work_item_fields as _update_work_item_fields,
    update_work_item_status as _update_work_item_status,
)

router = APIRouter(prefix="/api/work-items", tags=["work-items"])


VALID_WORK_TYPES = frozenset({"task", "action", "background", "goal"})
VALID_STATUSES = frozenset({
    "pending", "running", "blocked", "waiting_approval",
    "completed", "failed", "cancelled", "retrying",
    # Goal-style statuses retained for backward compat during migration.
    "active", "paused",
})


class CreateWorkItemRequest(BaseModel):
    title: str
    description: str = ""
    work_type: str = "task"
    parent_work_id: str | None = None
    parent_goal_id: str | None = None
    priority: int = 0
    dependencies: list[str] | None = None
    executable_plan: str | None = None
    status: str = "pending"
    # v1.0 goal-unification fields (used when work_type='goal')
    progress: float | None = None
    importance: float | None = None
    urgency: float | None = None
    deadline: str | None = None
    last_activity_at: str | None = None


class UpdateWorkItemRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    progress: float | None = None
    importance: float | None = None
    urgency: float | None = None
    deadline: str | None = None
    last_activity_at: str | None = None
    parent_work_id: str | None = None


@router.post("/")
async def create_work_item(body: CreateWorkItemRequest):
    """Create a work item of any type (task / action / background / goal)."""
    if body.work_type not in VALID_WORK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"work_type must be one of {sorted(VALID_WORK_TYPES)}",
        )

    return _create_work_item(
        title=body.title,
        description=body.description,
        work_type=body.work_type,
        parent_work_id=body.parent_work_id,
        parent_goal_id=body.parent_goal_id,
        priority=body.priority,
        dependencies=body.dependencies,
        executable_plan=body.executable_plan,
        status=body.status,
        progress=body.progress,
        importance=body.importance,
        urgency=body.urgency,
        deadline=body.deadline,
        last_activity_at=body.last_activity_at,
    )


@router.get("/")
async def list_work_items(
    work_type: str | None = None,
    status: str | None = None,
    parent_work_id: str | None = None,
    limit: int = 50,
):
    """List work items, optionally filtered by work_type / status / parent."""
    return _list_work_items(
        status=status, work_type=work_type, limit=limit,
    )


@router.get("/{item_id}")
async def get_work_item(item_id: str):
    item = _get_work_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return item


@router.get("/{item_id}/children")
async def get_children(item_id: str):
    """Return direct children of a work item (one level deep).

    For goal rows, this returns the actions/tasks nested under the goal.
    For full tree semantics, clients should recurse via this endpoint.
    """
    if not _get_work_item(item_id):
        raise HTTPException(status_code=404, detail="Work item not found")
    return _get_sub_work_items(item_id)


@router.patch("/{item_id}")
async def update_work_item(item_id: str, body: UpdateWorkItemRequest):
    """Update fields on a work item (title, progress, deadline, etc.).

    For status transitions, prefer POST /{item_id}/status which validates the
    state machine; this endpoint accepts status as a passthrough for cases
    where the caller has already validated.
    """
    update_kwargs = body.model_dump(exclude_unset=True)
    if not update_kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    item = _update_work_item_fields(item_id, **update_kwargs)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return item


@router.post("/{item_id}/status")
async def update_status(item_id: str, body: dict):
    """Transition a work item's status (validated by StateManager)."""
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")
    item = _update_work_item_status(item_id, new_status)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return item


@router.delete("/{item_id}")
async def delete_work_item(item_id: str):
    if not _get_work_item(item_id):
        raise HTTPException(status_code=404, detail="Work item not found")
    _delete_work_item(item_id)
    return {"status": "ok"}

"""Tasks API — manage work items via the unified WorkItem model.

v0.5.0: uses WorkItemCreated/StatusChanged/Deleted events and work_items projection.
"""
from fastapi import APIRouter, HTTPException

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.task_engine import task_engine

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/")
async def create_task(body: dict):
    """Create a task (WorkItem with work_type=task)."""
    name = (body.get("name") or body.get("title") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Task name is required")

    return task_engine.create_work_item(
        title=name,
        description=body.get("description", ""),
        work_type="task",
        parent_goal_id=body.get("parent_goal_id"),
        parent_work_id=body.get("parent_task_id"),
        priority=body.get("priority", 0),
        dependencies=body.get("dependencies"),
    )


@router.get("/")
async def list_tasks(status: str | None = None, limit: int = 50):
    return task_engine.list_work_items(status=status, work_type="task", limit=limit)


@router.get("/{task_id}")
async def get_task(task_id: str):
    item = task_engine.get_work_item(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    return item


@router.get("/{task_id}/subtasks")
async def get_subtasks(task_id: str):
    item = task_engine.get_work_item(task_id)
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_engine.get_sub_work_items(task_id)


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    if not task_engine.get_work_item(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    task_engine.delete_work_item(task_id)
    return {"status": "ok"}


@router.patch("/{task_id}/status")
async def update_task_status(task_id: str, body: dict):
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")
    item = task_engine.update_work_item_status(task_id, new_status)
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    return item


# ── Goal-scoped sub-items ────────────────────────────────────────────────

@router.post("/goal/{goal_id}")
async def create_goal_task(goal_id: str, body: dict):
    """Create a sub-item under a goal."""
    title = (body.get("name") or body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task name is required")
    return task_engine.create_work_item(
        title=title,
        description=body.get("description", ""),
        work_type=body.get("work_type", "task"),
        parent_goal_id=goal_id,
        parent_work_id=body.get("parent_task_id"),
        priority=body.get("priority", 0),
        executable_plan=body.get("executable_plan"),
    )


@router.get("/goal/{goal_id}")
async def list_goal_tasks(goal_id: str):
    return task_engine.get_work_item_tree(goal_id)

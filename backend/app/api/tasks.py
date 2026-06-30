"""Tasks API — manage tasks via the Task Engine."""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateTaskRequest, RunPlanningTaskRequest, UpdateTaskStatusRequest
from app.core.runtime.agent_manager import AgentManager
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.task_engine import task_engine

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/plan")
async def run_planning_task(body: RunPlanningTaskRequest):
    """Run multi-agent Planner + Worker pipeline via AgentBus."""
    request = (body.request or body.prompt).strip()
    if not request:
        raise HTTPException(status_code=400, detail="request is required (field name: 'request' or 'prompt')")
    manager = AgentManager(kernel)
    return await manager.run(user_request=request)


@router.post("/")
async def create_task(body: CreateTaskRequest):
    name = (body.name or body.title).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required (field name: 'name' or 'title')")

    task = task_engine.create_task(
        name=name,
        description=body.description,
        parent_goal_id=body.parent_goal_id,
        parent_task_id=body.parent_task_id,
        priority=body.priority,
        dependencies=body.dependencies,
    )
    return task


@router.get("/")
async def list_tasks(status: str | None = None, limit: int = 50):
    return task_engine.list_tasks(status=status, limit=limit)


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = task_engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/subtasks")
async def get_subtasks(task_id: str):
    if not task_engine.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return task_engine.get_subtasks(task_id)


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    task = task_engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    kernel.emit_event(
        type="TaskDeleted",
        aggregate_type="task",
        aggregate_id=task_id,
        actor="user",
    )
    return {"status": "ok"}


@router.get("/goals/{goal_id}/tree")
async def get_task_tree(goal_id: str):
    if not kernel.query_state("goals", id=goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return task_engine.get_task_tree(goal_id)


_STATUS_ALIASES = {
    "in_progress": "running",
    "in-progress": "running",
    "done": "completed",
    "cancel": "cancelled",
    "failure": "failed",
}


@router.patch("/{task_id}/status")
async def update_task_status(task_id: str, body: UpdateTaskStatusRequest):
    status = body.status
    if not status:
        raise HTTPException(status_code=400, detail="Status is required")

    normalized = _STATUS_ALIASES.get(status, status)
    try:
        task = task_engine.update_task_status(task_id, normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/dependencies-met")
async def check_dependencies(task_id: str):
    task = task_engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"met": task_engine.are_dependencies_met(task_id)}

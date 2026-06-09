"""Tasks API — manage tasks via the Task Engine."""

from fastapi import APIRouter, HTTPException

from app.core.runtime.agent_orchestrator import agent_orchestrator
from app.core.runtime.task_engine import task_engine

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/plan")
async def run_planning_task(body: dict):
    """Run Planner + Critic dynamic agent pipeline for a planning request."""
    request = body.get("request", "").strip()
    if not request:
        raise HTTPException(status_code=400, detail="request is required")
    return await agent_orchestrator.run_planning_task(request)


@router.post("/")
async def create_task(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    task = task_engine.create_task(
        name=name,
        description=body.get("description", ""),
        parent_goal_id=body.get("parent_goal_id"),
        parent_task_id=body.get("parent_task_id"),
        priority=body.get("priority", 0),
        dependencies=body.get("dependencies"),
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
    return task_engine.get_subtasks(task_id)


@router.get("/goals/{goal_id}/tree")
async def get_task_tree(goal_id: str):
    return task_engine.get_task_tree(goal_id)


@router.patch("/{task_id}/status")
async def update_task_status(task_id: str, body: dict):
    status = body.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="Status is required")
    task = task_engine.update_task_status(task_id, status)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/dependencies-met")
async def check_dependencies(task_id: str):
    return {"met": task_engine.are_dependencies_met(task_id)}

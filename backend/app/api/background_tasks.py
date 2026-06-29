"""Background Tasks API — manage long-running background tasks."""

from fastapi import APIRouter, HTTPException

from app.core.runtime.background_worker import background_worker

router = APIRouter(prefix="/api/tasks/background", tags=["background_tasks"])


@router.post("/")
async def create_background_task(body: dict):
    user_request = body.get("user_request", "").strip()
    if not user_request:
        raise HTTPException(status_code=400, detail="user_request is required")

    plan = body.get("plan")
    task = background_worker.create_task(user_request=user_request, plan=plan)
    return task


@router.get("/")
async def list_background_tasks(limit: int = 50):
    return background_worker.list_tasks(limit=limit)


@router.get("/{task_id}")
async def get_background_task(task_id: str):
    task = background_worker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

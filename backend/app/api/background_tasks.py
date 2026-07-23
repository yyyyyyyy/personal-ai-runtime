"""Background Tasks API — manage long-running background tasks.

Background tasks are a **Work subtype** stored as
``work_items(work_type='background')``. This HTTP surface remains for
operators / SPA compatibility; new clients should prefer ``/api/work-items``.
"""
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.models import CreateBackgroundTaskRequest
from app.core.runtime import read_ports
from app.core.runtime.kernel.constants import (
    AGGREGATE_WORK_ITEM,
    EVENT_WORK_ITEM_CREATED,
)
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["background_tasks"])


def _create_bg_task(user_request: str, plan: dict | None = None) -> dict:
    """Create a background work item via Kernel emit_event."""
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    plan_json = json.dumps(plan) if plan else None

    kernel.emit_event(
        EVENT_WORK_ITEM_CREATED,
        AGGREGATE_WORK_ITEM,
        task_id,
        payload={
            "title": user_request,
            "description": "",
            "work_type": "background",
            "parent_work_id": None,
            "parent_goal_id": None,
            "status": "pending",
            "priority": 0,
            "dependencies_json": None,
            "executable_plan": plan_json,
            "progress": 0.0,
            "created_at": now,
        },
        actor="user",
    )

    rows = read_ports.query_background_work_item(task_id)
    if not rows:
        raise RuntimeError(f"Background task {task_id} not found after creation")
    return rows


def _get_bg_task(task_id: str) -> dict | None:
    return read_ports.query_background_work_item(task_id)


def _list_bg_tasks(limit: int = 50) -> list[dict]:
    return read_ports.query_background_work_items(limit=limit)


@router.post("/")
async def create_background_task(body: CreateBackgroundTaskRequest):
    user_request = body.user_request.strip()
    if not user_request:
        raise HTTPException(status_code=400, detail="user_request is required")
    return _create_bg_task(user_request=user_request, plan=body.plan)


@router.get("/")
async def list_background_tasks(limit: int = 50):
    return _list_bg_tasks(limit=limit)


@router.get("/{task_id}")
async def get_background_task(task_id: str):
    task = _get_bg_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/cancel")
async def cancel_background_task(task_id: str):
    """Cancel a pending/running/waiting_approval background work item."""
    try:
        return read_ports.cancel_background_work_item(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

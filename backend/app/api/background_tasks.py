"""Background Tasks API — manage long-running background tasks.

Background tasks are a **Work subtype** (see Runtime
Algebra). New runtime code should treat them as Work with a background
lifecycle, not a separate conceptual layer. This HTTP surface remains for
operators / SPA; avoid introducing parallel task engines.
"""
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.models import CreateBackgroundTaskRequest
from app.core.runtime import read_ports
from app.core.runtime.kernel.constants import (
    AGGREGATE_BACKGROUND_TASK,
    EVENT_BG_TASK_CREATED,
)
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["background_tasks"])


def _create_bg_task(user_request: str, plan: dict | None = None) -> dict:
    """Create a background task via Kernel emit_event."""
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    plan_json = json.dumps(plan) if plan else None

    kernel.emit_event(
        EVENT_BG_TASK_CREATED,
        AGGREGATE_BACKGROUND_TASK,
        f"bg_{task_id}",
        payload={
            "task_id": task_id,
            "user_request": user_request,
            "plan_json": plan_json,
            "status": "pending",
            "progress": 0.0,
            "created_at": now,
        },
        actor="user",
    )

    rows = read_ports.query_background_task(task_id)
    if not rows:
        raise RuntimeError(f"Background task {task_id} not found after creation")
    return rows


def _get_bg_task(task_id: str) -> dict | None:
    return read_ports.query_background_task(task_id)


def _list_bg_tasks(limit: int = 50) -> list[dict]:
    return read_ports.query_background_tasks(limit=limit)


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

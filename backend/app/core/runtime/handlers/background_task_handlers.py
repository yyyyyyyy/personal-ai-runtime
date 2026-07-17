"""BackgroundTaskRequested handler — execute background task steps."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


@subscribe("BackgroundTaskRequested")
async def on_bg_task_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute a background task's steps via Scheduler."""
    from app.core.runtime.kernel.constants import (
        AGGREGATE_BACKGROUND_TASK,
        EVENT_BG_TASK_COMPLETED,
        EVENT_BG_TASK_STATUS_CHANGED,
    )
    from app.core.runtime.kernel_instance import kernel

    task_id = event.payload.get("task_id", "")
    plan_json = event.payload.get("plan_json", "{}")
    plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    steps = plan.get("steps", [])

    if not task_id:
        return

    aggregate_id = f"bg_{task_id}"

    def emit_status(status: str, progress: float, **extra: object) -> None:
        payload: dict[str, object] = {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            **extra,
        }
        ctx.emit(
            EVENT_BG_TASK_STATUS_CHANGED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload=payload,
            caused_by=event.id,
        )

    emit_status("running", 0.1)

    try:
        for i, step in enumerate(steps):
            tool_name = step.get("tool", "web_search")
            params = step.get("params", {"query": "background task"})

            cap = await kernel.invoke_capability(
                name=tool_name,
                args=params,
                actor="background",
                execution_id=ctx.execution_id,
                correlation_id=ctx.correlation_id,
            )
            if cap["status"] == "pending":
                progress = 0.1 + (0.8 * i / max(len(steps), 1))
                ctx.emit(
                    EVENT_BG_TASK_COMPLETED,
                    AGGREGATE_BACKGROUND_TASK,
                    aggregate_id,
                    payload={
                        "task_id": task_id,
                        "status": "waiting_approval",
                        "progress": progress,
                    },
                    caused_by=event.id,
                )
                return

            progress = 0.1 + (0.8 * (i + 1) / max(len(steps), 1))
            emit_status("running", progress)

        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={
                "task_id": task_id,
                "status": "completed",
                "progress": 1.0,
            },
            caused_by=event.id,
        )
    except Exception:
        logger.exception("BackgroundTaskRequested handler failed for task %s", task_id)
        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={"task_id": task_id, "status": "failed", "progress": 0.0},
            caused_by=event.id,
        )

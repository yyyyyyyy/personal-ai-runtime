"""BackgroundTaskRequested handler — execute background task steps."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe
from app.core.runtime.handlers.plan_runner import (
    PlanRunOutcome,
    parse_plan_steps,
    run_plan_steps,
)
from app.core.runtime.plan_resume import PlanResume

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
    if not task_id:
        return

    plan_json = event.payload.get("plan_json", "{}")
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

    try:
        steps = parse_plan_steps(plan_json)
    except ValueError as exc:
        logger.warning("Background task %s invalid plan: %s", task_id, exc)
        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={
                "task_id": task_id,
                "status": "failed",
                "progress": 0.0,
                "error": str(exc),
            },
            caused_by=event.id,
        )
        return

    if not steps:
        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={
                "task_id": task_id,
                "status": "failed",
                "progress": 0.0,
                "error": "empty plan",
            },
            caused_by=event.id,
        )
        return

    resume_from = int(event.payload.get("resume_from") or 0)
    previous_output = event.payload.get("previous_output")
    if previous_output is not None and not isinstance(previous_output, dict):
        previous_output = None

    plan_str = plan_json if isinstance(plan_json, str) else json.dumps(plan_json)

    def _resume_factory(outcome: PlanRunOutcome) -> PlanResume:
        return PlanResume(
            kind="background",
            resume_from=outcome.next_resume_from or 0,
            previous_output=outcome.previous_output,
            task_id=task_id,
            plan_json=plan_str,
        )

    emit_status("running", 0.1)

    try:
        outcome = await run_plan_steps(
            steps=steps,
            kernel=kernel,
            actor="background",
            execution_id=ctx.execution_id,
            correlation_id=ctx.correlation_id,
            resume_from=resume_from,
            previous_output=previous_output,
            resume_factory=_resume_factory,
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
        return

    if outcome.stopped_reason == "pending":
        progress = 0.1 + (0.8 * max(outcome.completed_steps, 0) / max(len(steps), 1))
        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={
                "task_id": task_id,
                "status": "waiting_approval",
                "progress": progress,
                "approval_id": outcome.pending_approval_id,
                "next_resume_from": outcome.next_resume_from,
                "results": [r.preview() for r in outcome.results],
            },
            caused_by=event.id,
        )
        return

    if outcome.stopped_reason == "failed":
        progress = 0.1 + (0.8 * max(outcome.completed_steps, 0) / max(len(steps), 1))
        emit_status("running", progress)
        ctx.emit(
            EVENT_BG_TASK_COMPLETED,
            AGGREGATE_BACKGROUND_TASK,
            aggregate_id,
            payload={
                "task_id": task_id,
                "status": "failed",
                "progress": progress,
                "results": [r.preview() for r in outcome.results],
            },
            caused_by=event.id,
        )
        return

    emit_status("running", 1.0)
    ctx.emit(
        EVENT_BG_TASK_COMPLETED,
        AGGREGATE_BACKGROUND_TASK,
        aggregate_id,
        payload={
            "task_id": task_id,
            "status": "completed",
            "progress": 1.0,
            "results": [r.preview() for r in outcome.results],
        },
        caused_by=event.id,
    )

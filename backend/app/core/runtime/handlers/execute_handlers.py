"""ExecuteRequested handler — run planned action steps via Scheduler."""

from __future__ import annotations

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


@subscribe("ExecuteRequested")
async def on_execute_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute a planned action's steps via Scheduler."""
    from app.core.runtime import read_ports
    from app.core.runtime.kernel_instance import kernel

    action_id = event.payload.get("action_id", "")
    if not action_id:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={"status": "error", "error": "missing action_id"},
            caused_by=event.id,
        )
        return

    action = read_ports.query_work_item(action_id)
    if not action:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={"status": "error", "error": "action not found"},
            caused_by=event.id,
        )
        return

    try:
        steps = parse_plan_steps(action.get("executable_plan") or "{}")
    except ValueError as exc:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={"status": "error", "error": str(exc)},
            caused_by=event.id,
        )
        return

    if not steps:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={
                "action_id": action_id,
                "status": "error",
                "error": "empty plan",
                "total_steps": 0,
                "completed_steps": 0,
                "results": [],
            },
            caused_by=event.id,
        )
        return

    resume_from = int(event.payload.get("resume_from") or 0)
    previous_output = event.payload.get("previous_output")
    if previous_output is not None and not isinstance(previous_output, dict):
        previous_output = None

    def _resume_factory(outcome: PlanRunOutcome) -> PlanResume:
        return PlanResume(
            kind="execute",
            resume_from=outcome.next_resume_from or 0,
            previous_output=outcome.previous_output,
            action_id=action_id,
        )

    outcome = await run_plan_steps(
        steps=steps,
        kernel=kernel,
        actor="executor",
        execution_id=ctx.execution_id,
        correlation_id=ctx.correlation_id,
        resume_from=resume_from,
        previous_output=previous_output,
        resume_factory=_resume_factory,
    )

    status = {
        "completed": "success",
        "pending": "waiting_approval",
        "failed": "error",
    }.get(outcome.stopped_reason, outcome.stopped_reason)

    ctx.emit(
        "ExecuteCompleted", "action", f"exec_{action_id}",
        payload={
            "action_id": action_id,
            "status": status,
            "total_steps": len(steps),
            "completed_steps": outcome.completed_steps,
            "resume_from": resume_from,
            "results": [r.preview() for r in outcome.results],
            **({
                "approval_id": outcome.pending_approval_id,
                "next_resume_from": outcome.next_resume_from,
            } if outcome.stopped_reason == "pending" else {}),
        },
        caused_by=event.id,
    )

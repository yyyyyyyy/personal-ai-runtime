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


def _emit_execute_completed(
    ctx: "ExecutionContext",
    event: "Event",
    action_id: str,
    *,
    status: str,
    **extra: object,
) -> None:
    from app.core.runtime.kernel.constants import EVENT_EXECUTE_COMPLETED

    ctx.emit(
        EVENT_EXECUTE_COMPLETED,
        "action",
        f"exec_{action_id}",
        payload={"action_id": action_id, "status": status, **extra},
        caused_by=event.id,
    )


def _sync_work_item_status(
    ctx: "ExecutionContext",
    event: "Event",
    action_id: str,
    status: str,
) -> None:
    from app.core.runtime.kernel.constants import (
        AGGREGATE_WORK_ITEM,
        EVENT_WORK_ITEM_STATUS_CHANGED,
    )

    ctx.emit(
        EVENT_WORK_ITEM_STATUS_CHANGED,
        AGGREGATE_WORK_ITEM,
        action_id,
        payload={"status": status},
        caused_by=event.id,
    )


@subscribe("ExecuteRequested")
async def on_execute_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute a planned action's steps via Scheduler."""
    from app.core.runtime import read_ports
    from app.core.runtime.kernel_instance import kernel

    action_id = event.payload.get("action_id", "")
    if not action_id:
        _emit_execute_completed(
            ctx, event, action_id, status="error", error="missing action_id",
        )
        return

    action = read_ports.query_work_item(action_id)
    if not action:
        _emit_execute_completed(
            ctx, event, action_id, status="error", error="action not found",
        )
        return

    # Approval resume re-enters while status is waiting_approval — mark running.
    if action.get("status") != "running":
        _sync_work_item_status(ctx, event, action_id, "running")

    try:
        steps = parse_plan_steps(action.get("executable_plan") or "{}")
    except ValueError as exc:
        _sync_work_item_status(ctx, event, action_id, "failed")
        _emit_execute_completed(
            ctx, event, action_id, status="error", error=str(exc),
        )
        return

    if not steps:
        _sync_work_item_status(ctx, event, action_id, "failed")
        _emit_execute_completed(
            ctx,
            event,
            action_id,
            status="error",
            error="empty plan",
            total_steps=0,
            completed_steps=0,
            results=[],
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

    wi_status = {
        "success": "completed",
        "waiting_approval": "waiting_approval",
        "error": "failed",
    }.get(status)
    if wi_status:
        _sync_work_item_status(ctx, event, action_id, wi_status)
        if wi_status == "completed":
            parent_goal_id = action.get("parent_goal_id")
            if parent_goal_id:
                read_ports.bump_parent_activity(parent_goal_id)
                read_ports.notify_goal_action_completed(
                    parent_goal_id,
                    action_id,
                    action.get("title", "") or "",
                )

    _emit_execute_completed(
        ctx,
        event,
        action_id,
        status=status,
        total_steps=len(steps),
        completed_steps=outcome.completed_steps,
        resume_from=resume_from,
        results=[r.preview() for r in outcome.results],
        **({
            "approval_id": outcome.pending_approval_id,
            "next_resume_from": outcome.next_resume_from,
        } if outcome.stopped_reason == "pending" else {}),
    )

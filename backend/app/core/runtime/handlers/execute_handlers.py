"""ExecuteRequested handler — run planned work-item steps via Scheduler.

Single event entry for both user-triggered execute and RuntimeLoop-dispatched
background work (``work_type='background'``). Branches preserve actor /
cancel_check / progress-stream semantics (INV-W5).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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


def _emit_work_item_progress(
    ctx: "ExecutionContext",
    event: "Event",
    action_id: str,
    progress: float,
) -> None:
    """Progress must go through WorkItemUpdated (StatusChanged only sets 1.0)."""
    from app.core.runtime.kernel.constants import (
        AGGREGATE_WORK_ITEM,
        EVENT_WORK_ITEM_UPDATED,
    )

    ctx.emit(
        EVENT_WORK_ITEM_UPDATED,
        AGGREGATE_WORK_ITEM,
        action_id,
        payload={"progress": float(progress)},
        caused_by=event.id,
    )


def _progress_ratio(completed_steps: int, total_steps: int) -> float:
    return 0.1 + (0.8 * max(completed_steps, 0) / max(total_steps, 1))


async def _run_work_plan(
    *,
    steps: list[dict[str, Any]],
    event: "Event",
    ctx: "ExecutionContext",
    action_id: str,
    actor: str,
    cancel_check: Callable[[], bool] | None = None,
) -> PlanRunOutcome:
    """Shared plan_runner call; actor / cancel_check injected by caller."""
    from app.core.runtime.kernel_instance import kernel

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

    return await run_plan_steps(
        steps=steps,
        kernel=kernel,
        actor=actor,
        execution_id=ctx.execution_id,
        correlation_id=ctx.correlation_id,
        resume_from=resume_from,
        previous_output=previous_output,
        resume_factory=_resume_factory,
        cancel_check=cancel_check,
    )


@subscribe("ExecuteRequested")
async def on_execute_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute a planned work item's steps via Scheduler."""
    from app.core.runtime import read_ports
    from app.core.runtime.execution import (
        clear_execution_cancel,
        is_execution_cancelled,
    )
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

    is_background = action.get("work_type") == "background"
    actor = "background" if is_background else "executor"
    exec_key = f"exec_{action_id}"

    def cancel_check() -> bool:
        if is_execution_cancelled(exec_key):
            return True
        if not is_background:
            return False
        rows = kernel.query_state("work_items", id=action_id, limit=1)
        return bool(rows and rows[0].get("status") == "cancelled")

    # Cancel may have arrived after RuntimeLoop dispatched but before this
    # handler acquired the row. Do NOT promote to running — durable status is
    # already authoritative (cancel API emitted WorkItemStatusChanged).
    if cancel_check():
        try:
            steps = parse_plan_steps(action.get("executable_plan") or "{}")
        except ValueError:
            steps = []
        clear_execution_cancel(exec_key)
        _emit_execute_completed(
            ctx, event, action_id, status="cancelled",
            total_steps=len(steps) if steps else 0,
            completed_steps=0, results=[],
        )
        return

    # Approval resume re-enters while status is waiting_approval — mark running.
    if action.get("status") != "running":
        _sync_work_item_status(ctx, event, action_id, "running")
        if is_background:
            _emit_work_item_progress(ctx, event, action_id, 0.1)

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

    try:
        outcome = await _run_work_plan(
            steps=steps,
            event=event,
            ctx=ctx,
            action_id=action_id,
            actor=actor,
            cancel_check=cancel_check if is_background else None,
        )
    except Exception:
        if is_background and cancel_check():
            _sync_work_item_status(ctx, event, action_id, "cancelled")
            clear_execution_cancel(exec_key)
            _emit_execute_completed(
                ctx, event, action_id, status="cancelled",
                total_steps=len(steps), completed_steps=0, results=[],
            )
            return
        _sync_work_item_status(ctx, event, action_id, "failed")
        _emit_execute_completed(
            ctx, event, action_id, status="error", error="handler_failed",
        )
        return

    resume_from = int(event.payload.get("resume_from") or 0)

    # Cancel acknowledged by plan_runner — durable cancel already emitted by API,
    # but re-stamp cancelled in case the handler raced past the API's emit.
    if outcome.stopped_reason == "cancelled" or (
        is_background and cancel_check()
    ):
        _sync_work_item_status(ctx, event, action_id, "cancelled")
        clear_execution_cancel(exec_key)
        if is_background:
            _emit_work_item_progress(
                ctx, event, action_id,
                _progress_ratio(outcome.completed_steps, len(steps)),
            )
        _emit_execute_completed(
            ctx,
            event,
            action_id,
            status="cancelled",
            total_steps=len(steps),
            completed_steps=outcome.completed_steps,
            resume_from=resume_from,
            results=[r.preview() for r in outcome.results],
        )
        return

    status = {
        "completed": "success",
        "pending": "waiting_approval",
        "failed": "error",
        "cancelled": "cancelled",
    }.get(outcome.stopped_reason, outcome.stopped_reason)

    wi_status = {
        "success": "completed",
        "waiting_approval": "waiting_approval",
        "error": "failed",
        "cancelled": "cancelled",
    }.get(status)

    if is_background and wi_status in (
        "waiting_approval", "failed", "completed",
    ):
        progress = (
            1.0 if wi_status == "completed"
            else _progress_ratio(outcome.completed_steps, len(steps))
        )
        _emit_work_item_progress(ctx, event, action_id, progress)

    if wi_status and wi_status != "cancelled":
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

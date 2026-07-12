"""Capability execution handlers — run inside the Scheduler → Handler chain.

Each handler resolves a capability-related event (approval, execute,
background task, inbox poll) via kernel.invoke_capability under governance.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


# ── Approve Handler ────────────────────────────────────────────────────


@subscribe("ApproveRequested")
async def on_approve_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Resolve a pending approval (approve or deny) via Scheduler."""
    from app.core.runtime.kernel_instance import kernel

    approval_id = event.payload.get("approval_id", "")
    decision = event.payload.get("decision", "deny")
    tool_name = event.payload.get("tool_name", "")
    tool_args = event.payload.get("tool_args", {})
    conv_id = event.payload.get("conv_id", "")
    tool_call_id = event.payload.get("tool_call_id", "")

    if not approval_id:
        ctx.emit(
            "ApproveCompleted", "approval", f"approve_{approval_id}",
            payload={"status": "error", "error": "missing approval_id"},
            caused_by=event.id,
        )
        return

    if decision == "deny":
        kernel.deny_approval(approval_id, action=tool_name, actor="user", reason="user_denied")
        ctx.emit(
            "ApproveCompleted", "approval", f"approve_{approval_id}",
            payload={
                "status": "denied",
                "approval_id": approval_id,
                "conv_id": conv_id,
                "tool_call_id": tool_call_id,
            },
            caused_by=event.id,
        )
        return

    # decision == "approve": execute capability then continue conversation
    cap_result = await kernel.invoke_capability(
        name=tool_name,
        args=tool_args,
        actor="user",
        pre_approved=True,
        approval_id=approval_id,
        execution_id=ctx.execution_id,
        correlation_id=ctx.correlation_id,
    )
    if cap_result["status"] == "success":
        result_str = cap_result["result"]
    else:
        result_str = json.dumps({"status": cap_result.get("status", "error"), "error": cap_result.get("error", "unknown")})

    # Resume conversation if context present
    assistant_message = None
    if conv_id and tool_call_id:
        from app.core.agents.brain import Brain
        from app.core.agents.conversation import ConversationManager

        conversation = ConversationManager(
            conversation_id=conv_id,
            correlation_id=ctx.correlation_id or None,
        )
        conversation.save_tool_result(result_str, tool_call_id)
        brain = Brain()
        try:
            assistant_message = await brain.continue_after_tool_result(conversation)
        except Exception as exc:
            logger.warning("Approve: conversation resume failed: %s", exc)

    ctx.emit(
        "ApproveCompleted", "approval", f"approve_{approval_id}",
        payload={
            "status": cap_result["status"],
            "result": result_str,
            "approval_id": approval_id,
            "conv_id": conv_id,
            "tool_call_id": tool_call_id,
            "assistant_message": assistant_message or "",
        },
        caused_by=event.id,
    )


# ── Execute Handler ────────────────────────────────────────────────────


@subscribe("ExecuteRequested")
async def on_execute_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute a planned action's steps via Scheduler."""
    from app.core.runtime import read_ports

    action_id = event.payload.get("action_id", "")
    if not action_id:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={"status": "error", "error": "missing action_id"},
            caused_by=event.id,
        )
        return

    # Load action's executable plan
    from app.core.runtime.kernel_instance import kernel

    action = read_ports.query_work_item(action_id)
    if not action:
        ctx.emit(
            "ExecuteCompleted", "action", f"exec_{action_id}",
            payload={"status": "error", "error": "action not found"},
            caused_by=event.id,
        )
        return
    plan_raw = action.get("executable_plan") or "{}"
    plan = json.loads(plan_raw) if isinstance(plan_raw, str) else plan_raw
    steps = plan.get("steps", [])

    results = []
    previous_output = None
    for i, step in enumerate(steps):
        tool_name = step["tool"]
        params = dict(step.get("params", {}))
        if step.get("depends_on_output") and previous_output:
            params["_previous_output"] = previous_output

        cap = await kernel.invoke_capability(name=tool_name, args=params, actor="executor", execution_id=ctx.execution_id, correlation_id=ctx.correlation_id)
        if cap["status"] == "success":
            step_status, step_result = "success", cap["result"]
        elif cap["status"] == "pending":
            step_status, step_result = "pending", json.dumps({"status": "pending_approval", "approval_id": cap.get("approval_id")})
        else:
            step_status, step_result = "failed", json.dumps({"error": cap.get("error", "unknown")})

        results.append({"step": i, "tool": tool_name, "status": step_status, "result_preview": str(step_result)[:500]})
        previous_output = {f"step_{i}_output": str(step_result)[:1000]}
        if step_status == "failed" and not step.get("continue_on_error"):
            break
        if step_status == "pending":
            break

    ctx.emit(
        "ExecuteCompleted", "action", f"exec_{action_id}",
        payload={
            "action_id": action_id,
            "total_steps": len(steps),
            "completed_steps": len([r for r in results if r["status"] == "success"]),
            "results": results,
        },
        caused_by=event.id,
    )


# ── Background Task Handler ────────────────────────────────────────────


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


# ── Inbox Poll Handler ─────────────────────────────────────────────────


@subscribe("InboxPollRequested")
async def on_inbox_poll_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Poll unread inbox via Scheduler under capability governance."""
    from app.core.runtime.kernel_instance import kernel

    limit = event.payload.get("limit", 20)
    cap = await kernel.invoke_capability(
        "check_inbox",
        {"unread_only": True, "limit": max(limit, 50)},
        actor="scheduler",
        execution_id=ctx.execution_id,
        correlation_id=ctx.correlation_id,
    )
    if cap.get("status") != "success":
        raw_error = cap.get("error", "check_inbox failed")
        if "EMAIL_USER" in raw_error or "EMAIL_PASS" in raw_error:
            raw_error = "Email credentials not configured"
        ctx.emit(
            "InboxPollCompleted", "inbox", f"inbox_{event.aggregate_id}",
            payload={"status": "error", "error": raw_error, "new_count": 0},
            caused_by=event.id,
        )
        return

    import json

    from app.product.inbox import apply_inbox_poll_payload

    result = cap["result"]
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}
    if not isinstance(result, dict):
        result = {}

    summary = await apply_inbox_poll_payload(result, execution_id=ctx.execution_id)
    if summary.get("status") == "error":
        ctx.emit(
            "InboxPollCompleted", "inbox", f"inbox_{event.aggregate_id}",
            payload={"status": "error", "error": summary.get("error", "inbox poll failed"), "new_count": 0},
            caused_by=event.id,
        )
        return

    ctx.emit(
        "InboxPollCompleted", "inbox", f"inbox_{event.aggregate_id}",
        payload={"status": "success", **summary},
        caused_by=event.id,
    )

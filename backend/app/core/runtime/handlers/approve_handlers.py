"""ApproveRequested handler — resolve pending approvals via Scheduler.

Lives in runtime.handlers (orchestration), not agents.
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
        result_str = json.dumps({
            "status": cap_result.get("status", "error"),
            "error": cap_result.get("error", "unknown"),
        })

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

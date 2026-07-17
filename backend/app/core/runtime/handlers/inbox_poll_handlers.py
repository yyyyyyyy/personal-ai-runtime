"""InboxPollRequested handler — poll unread inbox under capability governance."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution import ExecutionContext
    from app.core.runtime.kernel.event import Event


@subscribe("InboxPollRequested")
async def on_inbox_poll_requested(ctx: "ExecutionContext", event: "Event") -> None:
    """Poll unread inbox via Scheduler under capability governance."""
    from app.core.runtime.kernel_instance import kernel
    from app.product.inbox import apply_inbox_poll_payload

    limit = event.payload.get("limit", 20)
    cap = await kernel.invoke_capability(
        "check_inbox",
        {"unread_only": True, "limit": max(limit, 100)},
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
            payload={
                "status": "error",
                "error": summary.get("error", "inbox poll failed"),
                "new_count": 0,
            },
            caused_by=event.id,
        )
        return

    ctx.emit(
        "InboxPollCompleted", "inbox", f"inbox_{event.aggregate_id}",
        payload={"status": "success", **summary},
        caused_by=event.id,
    )

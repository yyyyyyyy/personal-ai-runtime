"""ExecuteRequested handler — run planned action steps via Scheduler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

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

        cap = await kernel.invoke_capability(
            name=tool_name,
            args=params,
            actor="executor",
            execution_id=ctx.execution_id,
            correlation_id=ctx.correlation_id,
        )
        if cap["status"] == "success":
            step_status, step_result = "success", cap["result"]
        elif cap["status"] == "pending":
            step_status, step_result = (
                "pending",
                json.dumps({"status": "pending_approval", "approval_id": cap.get("approval_id")}),
            )
        else:
            step_status, step_result = "failed", json.dumps({"error": cap.get("error", "unknown")})

        results.append({
            "step": i,
            "tool": tool_name,
            "status": step_status,
            "result_preview": str(step_result)[:500],
        })
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

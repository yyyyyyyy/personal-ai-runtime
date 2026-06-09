"""Executor — runs executable_plan steps from actions via Kernel capabilities."""

import json

from app.core.runtime.event_bus import EventType, event_bus
from app.core.runtime.kernel_instance import kernel
from app.core.telemetry.event_recorder import Event, event_recorder
from app.store.database import db


class Executor:
    """Executes LLM-generated action plans step by step through Kernel."""

    async def execute_action(self, action_id: str) -> dict:
        """Execute an action's executable_plan, recording each step result as an event."""
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if not row:
            return {"error": "Action not found"}

        action = dict(row)
        plan_str = action.get("executable_plan")
        if not plan_str:
            return {"error": "No executable plan defined"}

        try:
            plan = json.loads(plan_str)
        except json.JSONDecodeError:
            return {"error": "Invalid plan JSON"}

        steps = plan.get("steps", [])
        results = []
        previous_output: dict[str, object] = {}

        for i, step in enumerate(steps):
            tool_name = step["tool"]
            params = step.get("params", {})

            if step.get("depends_on_output") and previous_output:
                params["_previous_output"] = previous_output

            cap = await kernel.invoke_capability(
                name=tool_name,
                args=params,
                actor="executor",
            )
            if cap["status"] == "success":
                tool_result = cap["result"]
                step_status = "success"
            elif cap["status"] == "pending":
                tool_result = json.dumps({"status": "pending_approval", "approval_id": cap.get("approval_id")})
                step_status = "pending"
            else:
                tool_result = json.dumps({"error": cap.get("error", "unknown")})
                step_status = "failed"

            results.append({
                "step": i,
                "tool": tool_name,
                "status": step_status,
                "result_preview": str(tool_result)[:500],
            })

            event_recorder.record(Event(
                type="execution_step",
                summary=f"Step {i}: {tool_name} ({step_status})",
                payload={
                    "action_id": action_id,
                    "step_index": i,
                    "tool": tool_name,
                    "status": step_status,
                },
            ))

            previous_output = {f"step_{i}_output": str(tool_result)[:1000]}

            if step_status == "failed" and not step.get("continue_on_error"):
                break
            if step_status == "pending":
                break

        event_bus.publish(EventType.TASK_COMPLETED, {
            "task_id": f"action-{action_id}",
            "name": f"Executed action: {action.get('title', '')}",
            "step_results": results,
        })

        return {
            "action_id": action_id,
            "total_steps": len(steps),
            "completed_steps": len([r for r in results if r["status"] == "success"]),
            "results": results,
        }

    def generate_executable_plan(self, action_title: str, tool_context: str = "") -> dict:
        return {
            "steps": [
                {
                    "tool": "web_search",
                    "params": {"query": action_title},
                    "depends_on_output": False,
                    "continue_on_error": False,
                },
            ]
        }


executor = Executor()

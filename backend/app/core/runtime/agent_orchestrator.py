"""Agent Orchestrator — dynamic Planner + Critic pipeline for planning tasks."""

from __future__ import annotations

import uuid

from app.core.agents.critic import critic
from app.core.agents.planner import planner
from app.core.agents.world_model import world_model
from app.core.runtime.kernel_instance import kernel

# Capability whitelist per agent spec (Ticket-20 isolation)
AGENT_CAPABILITIES: dict[str, list[str]] = {
    "planner": ["get_current_time", "web_search", "list_directory", "read_file"],
    "critic": [],
    "brain": ["*"],
}


class AgentOrchestrator:
    """Runs ephemeral agent groups for structured tasks like project planning."""

    async def run_planning_task(self, user_request: str) -> dict:
        correlation_id = f"plan_{uuid.uuid4().hex[:12]}"
        context = world_model.to_prompt_context()

        task = kernel.create_task(
            name=f"Plan: {user_request[:60]}",
            plan={"summary": user_request},
            actor="user",
            correlation_id=correlation_id,
        )
        task_id = task["task_id"]

        planner_handle = kernel.spawn_agent(
            "planner",
            task_ref=task_id,
            actor="kernel",
            correlation_id=correlation_id,
            allowed_capabilities=AGENT_CAPABILITIES["planner"],
        )

        plan_result = await planner.plan(user_request, context=context)
        kernel.kill_agent(
            planner_handle,
            result={"status": "ok", "plan": plan_result},
            correlation_id=correlation_id,
        )

        critic_handle = kernel.spawn_agent(
            "critic",
            task_ref=task_id,
            actor="kernel",
            correlation_id=correlation_id,
            allowed_capabilities=AGENT_CAPABILITIES["critic"],
        )

        safe_steps = []
        for step in plan_result.get("steps", []):
            tool = step.get("tool", "")
            params = step.get("params", {})
            if critic.audit_step(tool, params):
                safe_steps.append(step)

        kernel.kill_agent(
            critic_handle,
            result={"status": "ok", "approved_steps": len(safe_steps)},
            correlation_id=correlation_id,
        )

        executed = []
        for step in safe_steps:
            tool = step.get("tool", "")
            if tool in ("write_file", "shell_exec", "send_email"):
                continue  # skip write ops in auto pipeline — user confirms separately
            cap = await kernel.invoke_capability(
                name=tool,
                args=step.get("params", {}),
                actor=f"agent:{planner_handle['agent_id']}",
                correlation_id=correlation_id,
            )
            executed.append({"tool": tool, "status": cap.get("status")})

        return {
            "correlation_id": correlation_id,
            "task_id": task_id,
            "goal": plan_result.get("goal", user_request),
            "plan": plan_result,
            "safe_steps": safe_steps,
            "executed": executed,
            "summary": self._format_summary(plan_result, safe_steps, executed),
        }

    def _format_summary(self, plan: dict, safe_steps: list, executed: list) -> str:
        lines = [f"## 规划结果：{plan.get('goal', '')}", ""]
        if safe_steps:
            lines.append("### 建议步骤")
            for i, s in enumerate(safe_steps, 1):
                lines.append(f"{i}. **{s.get('tool')}** — {s.get('reason', '')}")
        if executed:
            lines.append("")
            lines.append("### 已自动执行（只读工具）")
            for e in executed:
                lines.append(f"- {e['tool']}: {e['status']}")
        if plan.get("error"):
            lines.append(f"\n⚠️ 规划过程遇到问题：{plan['error']}")
        return "\n".join(lines)


agent_orchestrator = AgentOrchestrator()

"""Planner Agent — high-level reasoning with strong models.
Enhanced with self-healing replan capability (v0.2.0).
"""

import json

from app.core.agents.llm_router import llm_router
from app.core.runtime.runtime_config import runtime_config

PLANNER_PROMPT = """You are a strategic planner. Given a user request and context, produce a step-by-step execution plan.

Output ONLY valid JSON:
{
  "goal": "brief description",
  "steps": [{"tool": "tool_name", "params": {}, "reason": "why"}],
  "estimated_steps": 3, "confidence": 0.8
}

Available tools will be injected by the caller from the MCP registry at runtime."""
# NOTE: Tool list is injected dynamically via PlannerAgent.plan() which calls
# kernel.list_capability_definitions(). The hardcoded list above was stale
# and has been removed. See prompt_compiler.py for the canonical pattern.


REPLAN_PROMPT = """Previous plan failed. Generate a NEW plan avoiding failed tools.

Failed tools (DO NOT USE): {failing_tools}
Original request: {user_request}
Failed reason: {failure_reason}

Output ONLY valid JSON with different tools or approaches."""


class PlannerAgent:
    def __init__(self):
        self.client, self.provider = llm_router.get_client()

    async def plan(self, user_request: str, context: str = "") -> dict:
        messages = [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nUser request: {user_request}"},
        ]
        try:
            temp, max_tokens = runtime_config.get_generation_params()
            response = await self.client.chat.completions.create(  # type: ignore
                model=self.provider.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temp, max_tokens=max_tokens,
            )
            return json.loads(response.choices[0].message.content or "{}")
        except (json.JSONDecodeError, Exception) as e:
            return {"goal": user_request, "steps": [], "error": str(e)}

    async def replan(
        self, user_request: str, previous_plan: dict,
        failed_steps: list[dict], failing_tools: set[str],
        failure_reason: str = "",
    ) -> dict:
        prompt = REPLAN_PROMPT.format(
            user_request=user_request,
            failing_tools=", ".join(failing_tools) if failing_tools else "none",
            failure_reason=failure_reason or "Multiple tool failures",
        )
        messages = [
            {"role": "system", "content": "You are a strategic planner. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        try:
            temp, max_tokens = runtime_config.get_generation_params()
            response = await self.client.chat.completions.create(  # type: ignore
                model=self.provider.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temp, max_tokens=max_tokens,
            )
            plan = json.loads(response.choices[0].message.content or "{}")
            if failing_tools:
                steps = plan.get("steps", [])
                plan["steps"] = [s for s in steps if s.get("tool", "") not in failing_tools]
                plan["note"] = f"Filtered failing tools: {failing_tools}"
            return plan
        except (json.JSONDecodeError, Exception) as e:
            return {"goal": user_request, "steps": [], "error": str(e), "replan_reason": failure_reason}


planner = PlannerAgent()

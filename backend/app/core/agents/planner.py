"""Planner Agent — high-level reasoning with strong models (DeepSeek/Claude).

Takes user input + context, outputs a multi-step plan as JSON.
"""

import json

from app.core.agents.llm_router import llm_router
from app.core.runtime.runtime_config import runtime_config

PLANNER_PROMPT = """You are a strategic planner. Given a user request and context, produce a step-by-step execution plan.

Output ONLY valid JSON:
{
  "goal": "brief description of the goal",
  "steps": [
    {"tool": "tool_name", "params": {"param": "value"}, "reason": "why this step"}
  ],
  "estimated_steps": 3,
  "confidence": 0.8
}

Available tools: web_search, fetch_url, read_file, write_file, apply_patch, get_current_time, list_directory, search_files.
For write operations, add "requires_approval": true.
"""


class PlannerAgent:
    """High-level strategy agent using strong cloud models."""

    def __init__(self):
        self.client, self.provider = llm_router.get_client()

    async def plan(self, user_request: str, context: str = "") -> dict:
        """Generate a multi-step execution plan."""
        messages = [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nUser request: {user_request}"},
        ]

        try:
            temp, max_tokens = runtime_config.get_generation_params()
            response = await self.client.chat.completions.create(
                model=self.provider.model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            return {"goal": user_request, "steps": [], "error": str(e)}


planner = PlannerAgent()

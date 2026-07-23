"""Shared plan-step runner for Execute / BackgroundTask handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.runtime.plan_resume import PlanResume, register_plan_resume


@dataclass
class StepResult:
    step: int
    tool: str
    status: str  # success | failed | pending
    result: str
    approval_id: str | None = None

    def preview(self, limit: int = 500) -> dict[str, Any]:
        return {
            "step": self.step,
            "tool": self.tool,
            "status": self.status,
            "result_preview": self.result[:limit],
            **({"approval_id": self.approval_id} if self.approval_id else {}),
        }


@dataclass
class PlanRunOutcome:
    results: list[StepResult] = field(default_factory=list)
    stopped_reason: str = "completed"  # completed | failed | pending | empty | cancelled
    previous_output: dict[str, Any] | None = None
    pending_approval_id: str | None = None
    # Step index to continue from AFTER the pending tool is approved+executed.
    next_resume_from: int | None = None

    @property
    def completed_steps(self) -> int:
        return sum(1 for r in self.results if r.status == "success")


def parse_plan_steps(plan: Any) -> list[dict[str, Any]]:
    """Normalize a plan object/JSON string into a list of step dicts."""
    if isinstance(plan, str):
        try:
            plan = json.loads(plan) if plan.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid plan JSON: {exc}") from exc
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")
    return [s for s in steps if isinstance(s, dict)]


async def run_plan_steps(
    *,
    steps: list[dict[str, Any]],
    kernel: Any,
    actor: str,
    execution_id: str | None,
    correlation_id: str | None,
    resume_from: int = 0,
    previous_output: dict[str, Any] | None = None,
    resume_factory: Callable[[PlanRunOutcome], PlanResume] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PlanRunOutcome:
    """Run plan steps from ``resume_from``, stopping on failure or pending approval.

    Missing ``tool`` on a step is a hard failure (no silent default tool).
    When ``resume_factory`` is set, pending approvals register resume *before*
    returning so a fast Approve cannot race an empty registry.
    ``cancel_check`` is polled between steps for cooperative cancellation.
    """
    if not steps:
        return PlanRunOutcome(stopped_reason="empty")

    start = max(0, int(resume_from or 0))
    if start >= len(steps):
        return PlanRunOutcome(
            stopped_reason="completed",
            previous_output=previous_output,
        )

    results: list[StepResult] = []
    output = dict(previous_output) if previous_output else None

    for i in range(start, len(steps)):
        if cancel_check is not None and cancel_check():
            return PlanRunOutcome(
                results=results,
                stopped_reason="cancelled",
                previous_output=output,
            )

        step = steps[i]
        tool_name = str(step.get("tool") or "").strip()
        if not tool_name:
            results.append(StepResult(
                step=i,
                tool="",
                status="failed",
                result=json.dumps({"error": "missing tool on plan step"}),
            ))
            return PlanRunOutcome(
                results=results,
                stopped_reason="failed",
                previous_output=output,
            )

        params = dict(step.get("params") or {})
        if step.get("depends_on_output") and output:
            params["_previous_output"] = output

        cap = await kernel.invoke_capability(
            name=tool_name,
            args=params,
            actor=actor,
            execution_id=execution_id,
            correlation_id=correlation_id,
        )

        if cancel_check is not None and cancel_check():
            return PlanRunOutcome(
                results=results,
                stopped_reason="cancelled",
                previous_output=output,
            )

        if cap.get("status") == "success":
            step_result = str(cap.get("result", ""))
            results.append(StepResult(step=i, tool=tool_name, status="success", result=step_result))
            output = {f"step_{i}_output": step_result[:1000]}
            continue

        if cap.get("status") == "pending":
            approval_id = cap.get("approval_id")
            results.append(StepResult(
                step=i,
                tool=tool_name,
                status="pending",
                result=json.dumps({
                    "status": "pending_approval",
                    "approval_id": approval_id,
                }),
                approval_id=approval_id,
            ))
            outcome = PlanRunOutcome(
                results=results,
                stopped_reason="pending",
                previous_output=output,
                pending_approval_id=approval_id,
                next_resume_from=i + 1,
            )
            if resume_factory is not None and approval_id:
                register_plan_resume(
                    approval_id,
                    resume_factory(outcome),
                    kernel=kernel,
                )
            return outcome

        # failed / denied / error
        err = json.dumps({"error": cap.get("error", "unknown")})
        results.append(StepResult(step=i, tool=tool_name, status="failed", result=err))
        if step.get("continue_on_error"):
            output = {f"step_{i}_output": err[:1000]}
            continue
        return PlanRunOutcome(
            results=results,
            stopped_reason="failed",
            previous_output=output,
        )

    return PlanRunOutcome(
        results=results,
        stopped_reason="completed",
        previous_output=output,
    )

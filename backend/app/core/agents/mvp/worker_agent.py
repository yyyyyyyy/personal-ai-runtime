"""Worker Agent handler — MVP implementation.

Handles TaskPlanned events.  The Runtime dispatches by event.type so
the handler never needs to check event.type itself.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


@subscribe("TaskPlanned")
async def on_task_planned(ctx: "ExecutionContext", event: "Event") -> None:
    """Execute the first step of the plan and emit TaskCompleted."""
    plan = event.payload.get("plan", {})
    steps = plan.get("steps", [])
    step_summary = steps[0]["action"] if steps else "no_steps"

    logger.info(
        "Worker[%s]: executing step '%s' for %s",
        ctx.instance_id,
        step_summary,
        event.aggregate_id,
    )

    ctx.emit(
        event_type="TaskCompleted",
        aggregate_type="task",
        aggregate_id=event.aggregate_id,
        payload={
            "status": "completed",
            "step_executed": step_summary,
            "result_summary": f"Completed step: {step_summary}",
        },
        caused_by=event.id,
    )
    logger.info(
        "Worker[%s]: emitted TaskCompleted for %s",
        ctx.instance_id,
        event.aggregate_id,
    )

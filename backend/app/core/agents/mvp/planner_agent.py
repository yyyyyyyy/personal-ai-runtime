"""Planner Agent handlers — MVP implementation (EXPERIMENTAL).

THIS MODULE IS EXPERIMENTAL SKELETON CODE. The planner currently returns
hardcoded plans without calling the LLM-based PlannerAgent in
core/agents/planner.py. See the project review report for details.

To enable real multi-agent planning, wire this handler to use
PlannerAgent directly. DO NOT remove this module until the refactor
is complete.

Each handler is registered via @subscribe for a specific event type.
The Runtime dispatches events to the correct handler — handlers never
need to check event.type themselves.

This also means the same Handler can be assembled onto different
RuntimeProcess configurations.  TaskCompletedHandler can belong to
a Planner process, a Worker process, or a Reviewer process without
code duplication.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


@subscribe("TaskCreated")
async def on_task_created(ctx: "ExecutionContext", event: "Event") -> None:
    """Generate a plan when a new task is created."""
    task_name = event.payload.get("name", "untitled")
    plan = {
        "summary": f"Plan for: {task_name}",
        "steps": [
            {"action": "analyze", "tool": "web_search", "params": {"query": task_name}},
            {"action": "summarize", "tool": "read_file", "params": {"path": "/tmp/result"}},
        ],
    }
    ctx.emit(
        event_type="TaskPlanned",
        aggregate_type="task",
        aggregate_id=event.aggregate_id,
        payload={"plan": plan, "parent_task_id": event.aggregate_id},
        caused_by=event.id,
    )
    logger.info(
        "Planner[%s]: emitted TaskPlanned for %s",
        ctx.instance_id,
        event.aggregate_id,
    )


@subscribe("TaskCompleted")
async def on_task_completed(ctx: "ExecutionContext", event: "Event") -> None:
    """Confirm task completion."""
    logger.info(
        "Planner[%s]: confirmed TaskCompleted for %s",
        ctx.instance_id,
        event.aggregate_id,
    )

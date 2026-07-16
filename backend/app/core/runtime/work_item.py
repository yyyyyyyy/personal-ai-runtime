"""Deprecated shim — use ``scheduled_execution.ScheduledExecution`` (Lane A)."""

from app.core.runtime.scheduled_execution import (  # noqa: F401
    ExecutionPolicy,
    ScheduledExecution,
    ScheduledExecutionStatus,
    WorkItem,
    WorkItemStatus,
    policy_for_event,
)

__all__ = [
    "ExecutionPolicy",
    "ScheduledExecution",
    "ScheduledExecutionStatus",
    "WorkItem",
    "WorkItemStatus",
    "policy_for_event",
]

"""Deprecated shim — use ``scheduled_execution.ScheduledExecution`` (Lane A).

Do not confuse with domain ``work_items`` projections.
"""

import warnings

warnings.warn(
    "app.core.runtime.work_item is deprecated; import from "
    "app.core.runtime.scheduled_execution instead",
    DeprecationWarning,
    stacklevel=2,
)

from app.core.runtime.scheduled_execution import (  # noqa: E402,F401
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

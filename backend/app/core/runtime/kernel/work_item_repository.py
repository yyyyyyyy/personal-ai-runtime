"""Deprecated shim — use ``execution_repository``."""

from .execution_repository import (  # noqa: F401
    RECOVERABLE_STATUSES,
    STATUS_PENDING,
    STATUS_RETRYING,
    STATUS_RUNNING,
    read_scheduled_execution,
    read_scheduled_executions,
    read_work_items,
    recover_scheduled_executions,
    recover_work_items,
)

__all__ = [
    "RECOVERABLE_STATUSES",
    "STATUS_PENDING",
    "STATUS_RETRYING",
    "STATUS_RUNNING",
    "read_scheduled_execution",
    "read_scheduled_executions",
    "read_work_items",
    "recover_scheduled_executions",
    "recover_work_items",
]

"""Emit helpers for Execution aggregate events (ADR-0007 Step 1).

Plain functions only — not a runtime domain object. Schedulers call these
alongside existing persist_work_item dual-write paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.runtime.kernel.constants import (
    AGGREGATE_EXECUTION,
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_FAILED,
    EVENT_EXECUTION_REQUESTED,
    EVENT_EXECUTION_RETRIED,
    EVENT_EXECUTION_STARTED,
)

if TYPE_CHECKING:
    from app.core.runtime.kernel.event import Event
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.work_item import WorkItem


def _policy_payload(item: "WorkItem") -> dict:
    return {
        "timeout": item.policy.timeout_seconds,
        "max_retries": item.policy.max_retries,
        "retry_delay": item.policy.retry_delay_seconds,
    }


def emit_execution_requested(kernel: "Kernel", item: "WorkItem", actor: str) -> "Event":
    return kernel.emit_event(
        type=EVENT_EXECUTION_REQUESTED,
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=item.id,
        payload={
            "execution_id": item.id,
            "actor": actor,
            "handler_name": item.handler_name,
            "trigger_event_id": item.event_id,
            "trigger_event_seq": item.event_seq,
            "trigger_event_type": item.event_type,
            "instance_id": item.instance_id,
            "policy": _policy_payload(item),
            "correlation_id": item.correlation_id,
            "created_at": item.created_at,
            "event_seq": item.event_seq,
        },
        actor=actor,
        correlation_id=item.correlation_id or None,
        caused_by=item.event_id or None,
    )


def emit_execution_started(kernel: "Kernel", item: "WorkItem") -> "Event":
    return kernel.emit_event(
        type=EVENT_EXECUTION_STARTED,
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=item.id,
        payload={
            "execution_id": item.id,
            "attempt": item.retry_count + 1,
            "started_at": item.started_at or "",
        },
        actor="scheduler",
        correlation_id=item.correlation_id or None,
    )


def emit_execution_completed(
    kernel: "Kernel",
    item: "WorkItem",
    *,
    result_summary: str = "",
) -> "Event":
    return kernel.emit_event(
        type=EVENT_EXECUTION_COMPLETED,
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=item.id,
        payload={
            "execution_id": item.id,
            "completed_at": item.completed_at or "",
            "result_summary": result_summary,
        },
        actor="scheduler",
        correlation_id=item.correlation_id or None,
    )


def emit_execution_failed(
    kernel: "Kernel",
    item: "WorkItem",
    *,
    terminal: bool,
) -> "Event":
    return kernel.emit_event(
        type=EVENT_EXECUTION_FAILED,
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=item.id,
        payload={
            "execution_id": item.id,
            "failed_at": item.completed_at or "",
            "error": item.error or "",
            "attempt": item.retry_count,
            "terminal": terminal,
        },
        actor="scheduler",
        correlation_id=item.correlation_id or None,
    )


def emit_execution_retried(
    kernel: "Kernel",
    item: "WorkItem",
    *,
    reason: str,
    status: str,
) -> "Event":
    return kernel.emit_event(
        type=EVENT_EXECUTION_RETRIED,
        aggregate_type=AGGREGATE_EXECUTION,
        aggregate_id=item.id,
        payload={
            "execution_id": item.id,
            "attempt": item.retry_count,
            "reason": reason,
            "status": status,
        },
        actor="scheduler",
        correlation_id=item.correlation_id or None,
    )

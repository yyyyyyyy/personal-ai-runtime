"""Execution projectors — materialise handler_executions from Execution events (ADR-0007).

handler_executions is a projection of the Execution aggregate event stream.
ExecutionRequested is the sole aggregate creation event (no ExecutionCreated).
"""

from __future__ import annotations

import json

from .constants import (
    AGGREGATE_BACKGROUND_TASK,
    AGGREGATE_EXECUTION,
    EVENT_BG_TASK_COMPLETED,
    EVENT_BG_TASK_CREATED,
    EVENT_BG_TASK_STATUS_CHANGED,
)
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_EXECUTION] = ["handler_executions"]
_OWNED_TABLES[AGGREGATE_BACKGROUND_TASK] = ["background_tasks"]


def _policy_json(policy: dict) -> str:
    return json.dumps({
        "timeout": policy.get("timeout", 30.0),
        "max_retries": policy.get("max_retries", 3),
        "retry_delay": policy.get("retry_delay", 5.0),
    })


@projector("ExecutionRequested")
def _on_execution_requested(event: Event, conn) -> None:
    p = event.payload
    policy = p.get("policy") or {}
    conn.execute(
        """INSERT OR REPLACE INTO handler_executions
           (id, event_seq, event_id, event_type, handler_name, instance_id,
            status, retry_count, policy_json, correlation_id,
            created_at, started_at, completed_at, error)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, '', '', '')""",
        (
            event.aggregate_id,
            int(p.get("event_seq", 0)),
            p.get("trigger_event_id", ""),
            p.get("trigger_event_type", ""),
            p.get("handler_name", ""),
            p.get("instance_id", ""),
            _policy_json(policy),
            p.get("correlation_id", ""),
            p.get("created_at", event.ts),
        ),
    )


@projector("ExecutionStarted")
def _on_execution_started(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """UPDATE handler_executions
           SET status = 'running', started_at = ?
           WHERE id = ?""",
        (p.get("started_at", event.ts), event.aggregate_id),
    )


@projector("ExecutionRetried")
def _on_execution_retried(event: Event, conn) -> None:
    p = event.payload
    status = p.get("status", "retrying")
    conn.execute(
        """UPDATE handler_executions
           SET status = ?, retry_count = ?, error = ?
           WHERE id = ?""",
        (
            status,
            int(p.get("attempt", 0)),
            p.get("reason", ""),
            event.aggregate_id,
        ),
    )



@projector("ExecutionCompleted")
def _on_execution_completed(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """UPDATE handler_executions
           SET status = 'completed', completed_at = ?, error = ''
           WHERE id = ?""",
        (p.get("completed_at", event.ts), event.aggregate_id),
    )


@projector("ExecutionFailed")
def _on_execution_failed(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """UPDATE handler_executions
           SET status = 'failed', completed_at = ?, error = ?, retry_count = ?
           WHERE id = ?""",
        (
            p.get("failed_at", event.ts),
            p.get("error", ""),
            int(p.get("attempt", 0)),
            event.aggregate_id,
        ),
    )


# --- Background tasks (folded here to keep runtime_files zero-sum) ----------


@projector(EVENT_BG_TASK_CREATED)
def _on_background_task_created(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    conn.execute(
        """INSERT OR REPLACE INTO background_tasks
           (id, user_request, plan_json, status, progress, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            p.get("user_request", ""),
            p.get("plan_json"),
            p.get("status", "pending"),
            float(p.get("progress", 0)),
            p.get("created_at", event.ts),
            p.get("completed_at"),
        ),
    )


@projector(EVENT_BG_TASK_STATUS_CHANGED)
def _on_background_task_status_changed(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    fields = ["status = ?", "progress = ?"]
    params: list[object] = [p.get("status", "pending"), float(p.get("progress", 0))]
    if "completed_at" in p:
        fields.append("completed_at = ?")
        params.append(p["completed_at"])
    params.append(task_id)
    conn.execute(
        f"UPDATE background_tasks SET {', '.join(fields)} WHERE id = ?",
        params,
    )


@projector(EVENT_BG_TASK_COMPLETED)
def _on_background_task_completed(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    status = p.get("status", "completed")
    progress = float(p.get("progress", 1.0 if status == "completed" else 0.0))
    completed_at = p.get(
        "completed_at",
        event.ts if status in ("completed", "failed", "cancelled") else None,
    )
    conn.execute(
        """UPDATE background_tasks
           SET status = ?, progress = ?, completed_at = ?
           WHERE id = ?""",
        (status, progress, completed_at, task_id),
    )

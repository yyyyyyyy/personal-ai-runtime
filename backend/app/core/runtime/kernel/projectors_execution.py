"""Execution projectors — materialise handler_executions from Execution events (ADR-0007).

handler_executions is a projection of the Execution aggregate event stream.
ExecutionRequested is the sole aggregate creation event (no ExecutionCreated).
"""

from __future__ import annotations

import json

from .constants import AGGREGATE_EXECUTION
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_EXECUTION] = ["handler_executions"]


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

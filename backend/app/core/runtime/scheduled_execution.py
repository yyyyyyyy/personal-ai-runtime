"""ScheduledExecution — Lane A atomic unit of durable handler execution.

One ScheduledExecution = one invocation of one handler for one event.
Persisted in ``handler_executions`` (distinct from domain ``work_items``).

    Event → ScheduledExecution(s) → Scheduler → Handler
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

ScheduledExecutionStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "retrying",
]

# Backward-compatible alias for status type name used in some docs/tests.
WorkItemStatus = ScheduledExecutionStatus


@dataclass(frozen=True)
class ExecutionPolicy:
    """Execution parameters for a ScheduledExecution (Lane A)."""

    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 5.0

    @classmethod
    def default(cls) -> "ExecutionPolicy":
        return cls()


def policy_for_event(event_type: str) -> ExecutionPolicy:
    """Choose an ExecutionPolicy for a newly enqueued event."""
    if event_type == "ChatRequested":
        from app.config import settings

        return ExecutionPolicy(
            timeout_seconds=float(settings.total_tool_loop_timeout),
            max_retries=1,
            retry_delay_seconds=2.0,
        )
    return ExecutionPolicy.default()


@dataclass
class ScheduledExecution:
    """One invocation of a handler for a specific event (Lane A WORK unit)."""

    id: str = field(default_factory=lambda: f"wi_{uuid.uuid4().hex[:12]}")

    event_seq: int = 0
    event_id: str = ""
    event_type: str = ""
    handler_name: str = ""
    instance_id: str = ""

    status: ScheduledExecutionStatus = "pending"
    retry_count: int = 0
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy.default)

    correlation_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    error: str | None = None

    _event: object | None = field(default=None, repr=False, compare=False)

    def transition_to(self, status: ScheduledExecutionStatus) -> None:
        from app.core.runtime.task_engine import TaskStatus, state_manager

        state_manager.validate_transition(
            TaskStatus(self.status),
            TaskStatus(status),
        )
        self.status = status
        if status == "running" and self.started_at is None:
            self.started_at = datetime.now(UTC).isoformat()
        if status in ("completed", "failed"):
            self.completed_at = datetime.now(UTC).isoformat()

    def can_retry(self) -> bool:
        return self.retry_count < self.policy.max_retries

    def to_row(self) -> dict:
        import json

        return {
            "id": self.id,
            "event_seq": self.event_seq,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "handler_name": self.handler_name,
            "instance_id": self.instance_id,
            "status": self.status,
            "retry_count": self.retry_count,
            "policy_json": json.dumps({
                "timeout": self.policy.timeout_seconds,
                "max_retries": self.policy.max_retries,
                "retry_delay": self.policy.retry_delay_seconds,
            }),
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "started_at": self.started_at or "",
            "completed_at": self.completed_at or "",
            "error": self.error or "",
        }

    @classmethod
    def from_row(cls, row: dict) -> "ScheduledExecution":
        import json

        raw = row.get("policy_json") or "{}"
        policy_raw = json.loads(raw)
        policy = ExecutionPolicy(
            timeout_seconds=policy_raw.get("timeout", 30.0),
            max_retries=policy_raw.get("max_retries", 3),
            retry_delay_seconds=policy_raw.get("retry_delay", 5.0),
        )
        return cls(
            id=row["id"],
            event_seq=row.get("event_seq", 0),
            event_id=row.get("event_id", ""),
            event_type=row.get("event_type", ""),
            handler_name=row.get("handler_name", ""),
            instance_id=row.get("instance_id", ""),
            status=row["status"],
            retry_count=row.get("retry_count", 0),
            policy=policy,
            correlation_id=row.get("correlation_id", ""),
            created_at=row.get("created_at", ""),
            started_at=row.get("started_at") or None,
            completed_at=row.get("completed_at") or None,
            error=row.get("error") or None,
        )


# Deprecated alias — domain ``work_items`` is unrelated; do not use for new code.
WorkItem = ScheduledExecution

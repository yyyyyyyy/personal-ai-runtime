"""WorkItem — the atomic unit of durable execution.

A WorkItem represents ONE invocation of a handler for a specific event.
This is where Execution State lives — NOT in the Handler (stateless) and
NOT in the Agent (lifecycle).  The Handler is pure business logic; the
WorkItem is the Runtime's execution artifact.

Architecture:
    Event → WorkItem → Scheduler → Handler

The Scheduler no longer schedules Agents.  It schedules WorkItems.
This is the bridge from "Agent Runtime" to "Event Runtime".

State Machine:
    pending → running → completed
    pending → running → failed → retrying → running → completed

A WorkItem is persisted in handler_executions so that the Scheduler can
recover it after a restart (durable execution).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

WorkItemStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "retrying",
]


@dataclass(frozen=True)
class ExecutionPolicy:
    """Execution parameters for a WorkItem.

    Policy belongs to the WorkItem, NOT to the Handler.  The same handler
    (e.g. on_task_completed) can run with different policies depending on
    the context (3s timeout for Planner, 30s timeout for Reviewer).
    """

    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 5.0

    @classmethod
    def default(cls) -> "ExecutionPolicy":
        return cls()


@dataclass
class WorkItem:
    """One invocation of a handler for a specific event.

    This is the atomic scheduling unit.  The Scheduler owns the lifecycle:
    pending → running → completed/failed/retrying.

    Every WorkItem is persisted in handler_executions for durability.
    The _event field is the in-memory Event object — not persisted in the
    handler_executions table (the Event itself is already in event_log).
    """

    id: str = field(default_factory=lambda: f"wi_{uuid.uuid4().hex[:12]}")

    # --- what to execute ---
    event_seq: int = 0
    event_id: str = ""
    event_type: str = ""
    handler_name: str = ""
    instance_id: str = ""         # which AgentInstance owns this

    # --- execution state ---
    status: WorkItemStatus = "pending"
    retry_count: int = 0
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy.default)

    # --- timing ---
    correlation_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    # --- error ---
    error: str | None = None

    # --- in-memory only (not persisted to handler_executions) ---
    _event: object | None = field(default=None, repr=False, compare=False)

    def transition_to(self, status: WorkItemStatus) -> None:
        """Move to a new status, updating timestamps.

        Validates the transition through StateManager so that illegal
        state machine jumps (e.g. completed → running) raise immediately
        rather than silently corrupting handler_executions.
        """
        from app.core.runtime.state_manager import TaskStatus, state_manager
        state_manager.validate_transition(
            TaskStatus(self.status), TaskStatus(status),
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
    def from_row(cls, row: dict) -> "WorkItem":
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

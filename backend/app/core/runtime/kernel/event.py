"""Event primitive — the single immutable source of truth in the Runtime.

Per docs/RUNTIME_SPEC.md (v1.0 FROZEN), an Event is append-only, ordered (by `seq`),
immutable, and replayable. State and Memory are projections derived from Events;
the Event Log itself is the only thing that cannot be rebuilt.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _new_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Event:
    """An immutable fact. Frozen on purpose — once emitted, it never changes.

    Schema mirrors docs/RUNTIME_SPEC.md §1.1:
        seq            global monotonic ordinal (assigned by the log, not time)
        id             unique event id
        type           e.g. GoalCreated / GoalUpdated / GoalCompleted
        aggregate_type which kind of aggregate this belongs to (e.g. "goal")
        aggregate_id   concrete aggregate instance (e.g. "goal-123")
        actor          who triggered it (user / agent:xxx / kernel / scheduler)
        payload        event data
        caused_by      direct causal predecessor event id (one hop)
        correlation_id trace id shared by all events of one intent
        ts             wall-clock timestamp (display only; order by seq)
    """

    type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str = "system"
    caused_by: str | None = None
    correlation_id: str | None = None
    id: str = field(default_factory=_new_id)
    seq: int | None = None  # assigned by the Event Log on append
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def with_seq(self, seq: int) -> "Event":
        """Return a copy with the log-assigned sequence number."""
        return Event(
            type=self.type,
            aggregate_type=self.aggregate_type,
            aggregate_id=self.aggregate_id,
            payload=self.payload,
            actor=self.actor,
            caused_by=self.caused_by,
            correlation_id=self.correlation_id,
            id=self.id,
            seq=seq,
            ts=self.ts,
        )

    @classmethod
    def from_row(cls, row: Any) -> "Event":
        return cls(
            type=row["type"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            actor=row["actor"],
            caused_by=row["caused_by"],
            correlation_id=row["correlation_id"],
            id=row["id"],
            seq=row["seq"],
            ts=row["ts"],
        )

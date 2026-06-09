"""Projectors — turn the immutable Event Log into mutable State (materialized views).

Per RUNTIME_SPEC.md: State is a *projection* of Events, never written directly.
A projector consumes events and materializes a read model (here: the `goals` table).
Because the projection is fully derived, it can always be wiped and rebuilt by
replaying the Event Log — that is the core property this slice proves.
"""

from __future__ import annotations

import json
from typing import Callable

from .event import Event

# A projector handler applies a single event to a projection, using an open
# sqlite connection provided by the Kernel (Kernel Space owns storage access).
Handler = Callable[[Event, "object"], None]

_HANDLERS: dict[str, Handler] = {}
# aggregate_type -> projection table(s) this projector owns (used by rebuild).
_OWNED_TABLES: dict[str, list[str]] = {}


def projector(*event_types: str):
    """Register a handler for one or more event types."""

    def deco(fn: Handler) -> Handler:
        for et in event_types:
            _HANDLERS[et] = fn
        return fn

    return deco


def apply(event: Event, conn) -> None:
    """Apply one event to its projection, if a projector handles it."""
    handler = _HANDLERS.get(event.type)
    if handler is not None:
        handler(event, conn)


def owned_tables(aggregate_type: str) -> list[str]:
    return _OWNED_TABLES.get(aggregate_type, [])


# --- Goal projection ---------------------------------------------------------
# The `goals` table is the read model. These handlers are the ONLY writers to it
# in the event-sourced path.

_OWNED_TABLES["goal"] = ["goals"]


@projector("GoalCreated")
def _on_goal_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO goals
           (id, title, description, status, progress, importance, urgency,
            deadline, parent_id, created_at, updated_at, last_activity_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("title", ""),
            p.get("description", ""),
            p.get("status", "active"),
            p.get("progress", 0.0),
            p.get("importance", 0.5),
            p.get("urgency", 0.5),
            p.get("deadline"),
            p.get("parent_id"),
            p.get("created_at", event.ts),
            event.ts,
            event.ts,
        ),
    )


@projector("GoalUpdated")
def _on_goal_updated(event: Event, conn) -> None:
    p = event.payload
    updatable = (
        "title",
        "description",
        "status",
        "progress",
        "importance",
        "urgency",
        "deadline",
        "parent_id",
    )
    fields = [k for k in updatable if k in p]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [p[k] for k in fields]
    params += [event.ts, event.ts, event.aggregate_id]
    conn.execute(
        f"UPDATE goals SET {set_clause}, updated_at = ?, last_activity_at = ? WHERE id = ?",
        params,
    )


@projector("GoalCompleted")
def _on_goal_completed(event: Event, conn) -> None:
    conn.execute(
        "UPDATE goals SET status = 'completed', progress = 1.0, updated_at = ?, last_activity_at = ? WHERE id = ?",
        (event.ts, event.ts, event.aggregate_id),
    )


@projector("GoalDeleted")
def _on_goal_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM goals WHERE id = ?", (event.aggregate_id,))


@projector("GoalTouched")
def _on_goal_touched(event: Event, conn) -> None:
    """Bump activity timestamps without changing goal fields (e.g. when a
    sub-action is created/updated). Keeps the goals projection write inside
    Kernel Space instead of leaking into the Actions API handlers."""
    conn.execute(
        "UPDATE goals SET last_activity_at = ?, updated_at = ? WHERE id = ?",
        (event.ts, event.ts, event.aggregate_id),
    )


# --- Approval projection -----------------------------------------------------
# The `approvals` table is the read model for governance.

_OWNED_TABLES["approval"] = ["approvals"]


@projector("ApprovalRequested")
def _on_approval_requested(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO approvals (id, task_id, action, params, proposed_by, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
        (
            event.aggregate_id,
            p.get("ctx", {}).get("task_id"),
            p.get("action", ""),
            json.dumps(p.get("ctx", {}).get("args", {})),
            event.actor,
            event.ts,
        ),
    )


@projector("ApprovalGranted", "ApprovalDenied")
def _on_approval_resolved(event: Event, conn) -> None:
    status = "approved" if event.type == "ApprovalGranted" else "denied"
    conn.execute(
        "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (status, event.ts, event.actor, event.aggregate_id),
    )


# --- Memory projection -------------------------------------------------------
# The `memories` table is the projection for derived beliefs.

_OWNED_TABLES["memory"] = ["memories"]


@projector("MemoryDerived")
def _on_memory_derived(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO memories
           (id, category, content, source, embedding_id, confidence, derived_from_event, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("category", "general"),
            p.get("content", ""),
            p.get("source", ""),
            p.get("embedding_id"),
            p.get("confidence", 0.5),
            p.get("derived_from_event", event.caused_by),
            event.ts,
        ),
    )


@projector("MemoryDecayed")
def _on_memory_decayed(event: Event, conn) -> None:
    p = event.payload
    new_confidence = float(p.get("confidence", 0.1))
    conn.execute(
        "UPDATE memories SET confidence = ?, decayed_at = ? WHERE id = ?",
        (new_confidence, event.ts, event.aggregate_id),
    )


@projector("MemoryRevoked")
def _on_memory_revoked(event: Event, conn) -> None:
    """A memory has been contradicted by new evidence — set confidence to 0."""
    conn.execute(
        "UPDATE memories SET confidence = 0.0, decayed_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )


@projector("MemoryUpdated")
def _on_memory_updated(event: Event, conn) -> None:
    p = event.payload
    updatable = ("content", "category", "source", "confidence", "embedding_id")
    fields = [k for k in updatable if k in p]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [p[k] for k in fields]
    params.append(event.aggregate_id)
    conn.execute(
        f"UPDATE memories SET {set_clause} WHERE id = ?",
        params,
    )


@projector("MemoryDeleted")
def _on_memory_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM memories WHERE id = ?", (event.aggregate_id,))


# --- Task / Agent projection -------------------------------------------------

_OWNED_TABLES["task"] = ["tasks"]


@projector("TaskCreated")
def _on_task_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO tasks
           (id, name, description, parent_goal_id, parent_task_id, status, priority,
            dependencies_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("name", ""),
            p.get("description", ""),
            p.get("parent_goal_id"),
            p.get("parent_task_id"),
            p.get("priority", 0),
            p.get("dependencies_json"),
            event.ts,
            event.ts,
        ),
    )


@projector("TaskStarted")
def _on_task_started(event: Event, conn) -> None:
    conn.execute(
        "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )


@projector("TaskCompleted")
def _on_task_completed(event: Event, conn) -> None:
    conn.execute(
        "UPDATE tasks SET status = 'completed', updated_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )


@projector("TaskFailed")
def _on_task_failed(event: Event, conn) -> None:
    conn.execute(
        "UPDATE tasks SET status = 'failed', updated_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )


@projector("TaskStatusChanged")
def _on_task_status_changed(event: Event, conn) -> None:
    """Generic task status transition (task_engine path)."""
    status = event.payload.get("status")
    if not status:
        return
    conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
        (status, event.ts, event.aggregate_id),
    )


# --- Action projection -------------------------------------------------------
# The `actions` table is the read model for goal sub-actions.

_OWNED_TABLES["action"] = ["actions"]


@projector("ActionCreated")
def _on_action_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO actions
           (id, goal_id, title, status, executable_plan, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("goal_id", ""),
            p.get("title", ""),
            p.get("status", "pending"),
            p.get("executable_plan"),
            p.get("created_at", event.ts),
            p.get("completed_at"),
        ),
    )


@projector("ActionUpdated")
def _on_action_updated(event: Event, conn) -> None:
    p = event.payload
    updatable = ("title", "status", "executable_plan", "completed_at")
    fields = [k for k in updatable if k in p]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [p[k] for k in fields]
    params.append(event.aggregate_id)
    conn.execute(
        f"UPDATE actions SET {set_clause} WHERE id = ?",
        params,
    )


@projector("ActionDeleted")
def _on_action_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM actions WHERE id = ?", (event.aggregate_id,))

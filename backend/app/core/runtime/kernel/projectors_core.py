import json

# --- Goal projection ---------------------------------------------------------
# The `goals` table is the read model. These handlers are the ONLY writers to it
# in the event-sourced path.
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

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
        "last_activity_at",
    )
    fields = [k for k in updatable if k in p]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [p[k] for k in fields]
    params.append(event.ts)
    if "last_activity_at" in fields:
        params.append(event.aggregate_id)
        conn.execute(
            f"UPDATE goals SET {set_clause}, updated_at = ? WHERE id = ?",
            params,
        )
    else:
        params += [event.ts, event.aggregate_id]
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
        """INSERT OR REPLACE INTO approvals (id, task_id, action, params, proposed_by, status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            event.aggregate_id,
            p.get("ctx", {}).get("task_id"),
            p.get("action", ""),
            json.dumps(p.get("ctx", {}).get("args", {})),
            event.actor,
            event.ts,
            p.get("expires_at"),
        ),
    )


@projector("ApprovalExpired")
@projector("ApprovalGranted", "ApprovalDenied")
def _on_approval_resolved(event: Event, conn) -> None:
    if event.type == "ApprovalGranted":
        status = "approved"
    elif event.type == "ApprovalDenied":
        status = "denied"
    else:
        status = "expired"
    conn.execute(
        "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (status, event.ts, event.actor, event.aggregate_id),
    )


# --- Memory projection -------------------------------------------------------
# The `memories` table is the projection for derived beliefs.

_OWNED_TABLES["memory"] = ["memories"]


def origin_from_actor(actor: str) -> str:
    """Map event actor to memory origin (Meaning Boundary G2).

    Only explicit user-authored events are self_report; everything else is claim.
    """
    if actor == "user":
        return "self_report"
    return "claim"


def initial_claim_status(origin: str) -> str | None:
    """Meaning Boundary G1: claims start proposed; self-reports skip Authority."""
    return "proposed" if origin == "claim" else None


def _set_claim_status_if_claim(conn, memory_id: str, status: str) -> None:
    """Apply epistemic status only to origin=claim rows."""
    row = conn.execute(
        "SELECT origin FROM memories WHERE id = ?", (memory_id,)
    ).fetchone()
    if row and row["origin"] == "claim":
        conn.execute(
            "UPDATE memories SET claim_status = ? WHERE id = ?",
            (status, memory_id),
        )


@projector("MemoryDerived")
def _on_memory_derived(event: Event, conn) -> None:
    p = event.payload
    origin = origin_from_actor(event.actor)
    claim_status = initial_claim_status(origin)
    conn.execute(
        """INSERT OR REPLACE INTO memories
           (id, category, content, source, embedding_id, confidence,
            derived_from_event, created_at, origin, claim_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("category", "general"),
            p.get("content", ""),
            p.get("source", ""),
            p.get("embedding_id"),
            p.get("confidence", 0.5),
            p.get("derived_from_event", event.caused_by),
            event.ts,
            origin,
            claim_status,
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


@projector("TaskDeleted")
def _on_task_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM tasks WHERE id = ?", (event.aggregate_id,))


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


# --- Claim authority projection (Meaning Boundary G1) ------------------------


@projector("ClaimRatified")
def _on_claim_ratified(event: Event, conn) -> None:
    _set_claim_status_if_claim(conn, event.aggregate_id, "ratified")


@projector("ClaimRejected")
def _on_claim_rejected(event: Event, conn) -> None:
    _set_claim_status_if_claim(conn, event.aggregate_id, "rejected")


@projector("ClaimContested")
def _on_claim_contested(event: Event, conn) -> None:
    _set_claim_status_if_claim(conn, event.aggregate_id, "contested")


@projector("ClaimReleased")
def _on_claim_released(event: Event, conn) -> None:
    _set_claim_status_if_claim(conn, event.aggregate_id, "released")


@projector("ClaimReopened")
def _on_claim_reopened(event: Event, conn) -> None:
    _set_claim_status_if_claim(conn, event.aggregate_id, "contested")


@projector("ClaimRevised")
def _on_claim_revised(event: Event, conn) -> None:
    p = event.payload
    row = conn.execute(
        "SELECT origin FROM memories WHERE id = ?", (event.aggregate_id,)
    ).fetchone()
    if not row or row["origin"] != "claim":
        return
    updatable = ("content", "confidence")
    fields = [k for k in updatable if k in p]
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = [p[k] for k in fields]
        params.append(event.aggregate_id)
        conn.execute(
            f"UPDATE memories SET {set_clause} WHERE id = ?",
            params,
        )
    conn.execute(
        "UPDATE memories SET claim_status = 'proposed' WHERE id = ?",
        (event.aggregate_id,),
    )



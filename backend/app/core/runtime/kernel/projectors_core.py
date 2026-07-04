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


# --- Unified WorkItem projection (v0.5.0: merges task + action) ------------
# The `work_items` table fully supersedes both `tasks` and `actions`.

_OWNED_TABLES["work_item"] = ["work_items"]


@projector("WorkItemCreated")
def _on_work_item_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO work_items
           (id, title, description, work_type, parent_work_id, parent_goal_id,
            status, priority, dependencies_json, executable_plan, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("title", ""),
            p.get("description", ""),
            p.get("work_type", "task"),
            p.get("parent_work_id"),
            p.get("parent_goal_id"),
            p.get("status", "pending"),
            p.get("priority", 0),
            p.get("dependencies_json"),
            p.get("executable_plan"),
            p.get("created_at", event.ts),
            event.ts,
        ),
    )


@projector("WorkItemUpdated")
def _on_work_item_updated(event: Event, conn) -> None:
    p = event.payload
    updatable = ("title", "description", "status", "priority",
                 "dependencies_json", "executable_plan", "completed_at",
                 "parent_work_id", "parent_goal_id")
    fields = [k for k in updatable if k in p]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [p[k] for k in fields]
    params.append(event.ts)
    params.append(event.aggregate_id)
    conn.execute(
        f"UPDATE work_items SET {set_clause}, updated_at = ? WHERE id = ?",
        params,
    )


@projector("WorkItemStatusChanged")
def _on_work_item_status_changed(event: Event, conn) -> None:
    status = event.payload.get("status")
    if not status:
        return
    extra = []
    vals = [status, event.ts]
    if status == "completed":
        extra.append("completed_at = ?")
        vals.append(event.ts)
    completed_clause = ", " + ", ".join(extra) if extra else ""
    vals.append(event.aggregate_id)
    conn.execute(
        f"UPDATE work_items SET status = ?, updated_at = ?{completed_clause} WHERE id = ?",
        vals,
    )


@projector("WorkItemDeleted")
def _on_work_item_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM work_items WHERE id = ?", (event.aggregate_id,))


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



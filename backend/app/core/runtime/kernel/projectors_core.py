import json

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

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


@projector("ApprovalGranted")
def _on_approval_granted(event: Event, conn) -> None:
    conn.execute(
        "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        ("approved", event.ts, event.actor, event.aggregate_id),
    )


@projector("ApprovalDenied")
def _on_approval_denied(event: Event, conn) -> None:
    p = event.payload
    status = "expired" if p.get("reason") == "auto_expired" else "denied"
    # Idempotent: only transition pending rows (safe under duplicate emits).
    conn.execute(
        "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? "
        "WHERE id = ? AND status = 'pending'",
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
            derived_from_event, created_at, origin, claim_status,
            source_document_id, source_document_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            p.get("source_document_id"),
            p.get("source_document_name"),
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


# --- WorkItem projection -------------------------------------------------------
# The `work_items` table holds all work types (task / action / background / goal).

_OWNED_TABLES["work_item"] = ["work_items"]


@projector("WorkItemCreated")
def _on_work_item_created(event: Event, conn) -> None:
    p = event.payload
    # Goal columns: WorkItemCreated with work_type='goal' populates
    # progress/importance/urgency/deadline/last_activity_at; other work_types
    # fall back to schema defaults (progress=0, importance=urgency=0.5,
    # deadline/last_activity_at=NULL).
    conn.execute(
        """INSERT OR REPLACE INTO work_items
           (id, title, description, work_type, parent_work_id, parent_goal_id,
            status, priority, dependencies_json, executable_plan, created_at, updated_at,
            progress, importance, urgency, deadline, last_activity_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            # v1.0 goal fields — only present in payload when work_type='goal'.
            # Defaults match the schema server_default so non-goal rows are
            # byte-identical to pre-v1.0 rebuild output.
            p.get("progress", 0),
            p.get("importance", 0.5),
            p.get("urgency", 0.5),
            p.get("deadline"),
            p.get("last_activity_at"),
        ),
    )

    # When a new child is created under a goal, recompute the parent's progress
    # so the count of children stays consistent. Without this, adding a child
    # after some siblings are already completed would leave the parent's
    # progress stale until the next status change.
    _recalculate_parent_goal_progress(conn, event.aggregate_id, event.ts)


@projector("WorkItemUpdated")
def _on_work_item_updated(event: Event, conn) -> None:
    p = event.payload
    updatable = ("title", "description", "status", "priority",
                 "dependencies_json", "executable_plan", "completed_at",
                 "parent_work_id", "parent_goal_id",
                 "progress", "importance", "urgency", "deadline",
                 "last_activity_at")
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
        # v1.0 fix: ensure progress is 1.0 when a goal/task is completed.
        extra.append("progress = 1.0")
    completed_clause = ", " + ", ".join(extra) if extra else ""
    vals.append(event.aggregate_id)
    conn.execute(
        f"UPDATE work_items SET status = ?, updated_at = ?{completed_clause} WHERE id = ?",
        vals,
    )

    # Derive parent goal progress when a child changes status.
    # Pure projection (same transaction) — rebuild produces byte-identical
    # state because the same event sequence replays the same calculation.
    _recalculate_parent_goal_progress(conn, event.aggregate_id, event.ts)


def _recalculate_parent_goal_progress(
    conn, child_id: str, ts: str, parent_id_hint: str | None = None,
) -> None:
    """When a child work_item's status changes or is created/deleted, recompute
    its parent goal's progress as completed_children / total_children (only if
    the parent is a goal). Pure SQL within the projector's transaction — no
    event emission, so no recursion risk.

    Progress = completed / total (only children of this parent counted).

    ``parent_id_hint`` lets callers that already know the parent (e.g. delete
    path, which has to capture it before the row goes away) skip the lookup.
    """
    parent_id = parent_id_hint
    if parent_id is None:
        # Look up the parent reference of the child that just changed.
        row = conn.execute(
            "SELECT parent_work_id, parent_goal_id FROM work_items WHERE id = ?",
            (child_id,),
        ).fetchone()
        if row is None:
            return
        parent_id = row["parent_work_id"] or row["parent_goal_id"]
    if not parent_id:
        return

    # Only recompute if the parent is a goal (tasks don't track progress).
    parent = conn.execute(
        "SELECT work_type FROM work_items WHERE id = ?", (parent_id,),
    ).fetchone()
    if parent is None or parent["work_type"] != "goal":
        return

    # Count children and completed children. Children reference the goal
    # via either parent_work_id or parent_goal_id.
    children = conn.execute(
        "SELECT status FROM work_items "
        "WHERE parent_work_id = ? OR parent_goal_id = ?",
        (parent_id, parent_id),
    ).fetchall()
    if not children:
        # No children left — reset progress to 0 (avoids stale non-zero value).
        conn.execute(
            "UPDATE work_items SET progress = 0, last_activity_at = ?, updated_at = ? "
            "WHERE id = ?",
            (ts, ts, parent_id),
        )
        return
    total = len(children)
    completed = sum(1 for c in children if c["status"] == "completed")
    progress = completed / total if total > 0 else 0.0

    conn.execute(
        "UPDATE work_items SET progress = ?, last_activity_at = ?, updated_at = ? "
        "WHERE id = ?",
        (progress, ts, ts, parent_id),
    )


@projector("WorkItemDeleted")
def _on_work_item_deleted(event: Event, conn) -> None:
    # Capture parent reference before delete so we can recompute
    # parent goal progress after the child row is gone.
    row = conn.execute(
        "SELECT parent_work_id, parent_goal_id FROM work_items WHERE id = ?",
        (event.aggregate_id,),
    ).fetchone()
    parent_id = row["parent_work_id"] or row["parent_goal_id"] if row else None

    conn.execute("DELETE FROM work_items WHERE id = ?", (event.aggregate_id,))

    if parent_id:
        _recalculate_parent_goal_progress(conn, event.aggregate_id, event.ts)


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


# --- User Profile projection --------------------------------------------------

@projector("UserProfileUpdated")
def _on_user_profile_updated(event: Event, conn) -> None:
    p = event.payload
    category = p["category"]
    conn.execute(
        """INSERT OR REPLACE INTO user_profile
           (id, category, data_json, confidence, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (category, category, p["data_json"], p["confidence"], event.ts),
    )


# --- Notification projection --------------------------------------------------

_OWNED_TABLES["notification"] = ["notifications"]


@projector("NotificationCreated")
def _on_notification_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO notifications
           (id, type, title, content, read,
            related_id, related_type, notification_type, dedup_key, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("type", ""),
            p.get("title", ""),
            p.get("content", ""),
            p.get("related_id"),
            p.get("related_type"),
            p.get("notification_type"),
            p.get("dedup_key"),
            p.get("created_at", event.ts),
        ),
    )


@projector("NotificationUpdated")
def _on_notification_updated(event: Event, conn) -> None:
    p = event.payload
    if "related_id" in p or "related_type" in p:
        conn.execute(
            """UPDATE notifications
               SET content = ?, related_id = COALESCE(?, related_id),
                   related_type = COALESCE(?, related_type)
               WHERE id = ?""",
            (
                p.get("content", ""),
                p.get("related_id"),
                p.get("related_type"),
                event.aggregate_id,
            ),
        )
    else:
        conn.execute(
            "UPDATE notifications SET content = ? WHERE id = ?",
            (p.get("content", ""), event.aggregate_id),
        )


@projector("NotificationRead")
def _on_notification_read(event: Event, conn) -> None:
    if event.aggregate_id == "all":
        conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        return
    conn.execute(
        "UPDATE notifications SET read = 1 WHERE id = ?",
        (event.aggregate_id,),
    )


"""Typed query-construction helpers for Kernel read paths.

Centralises the patterns that were previously hand-written across the Kernel
mixins (``WHERE`` clause assembly, ``LIMIT``/``ORDER BY`` injection,
``IN (...)`` placeholders). Goals:

- No ad-hoc f-strings in call sites — every fragment is built here.
- ``int(limit)`` coercion lives in exactly one place, with a sane ceiling.
- ``ORDER BY`` clauses are validated against an allowlist dict so callers
  cannot inject arbitrary SQL via the ``order`` parameter — unknown keys
  fall back to the default rather than being interpolated.

Fragment helpers emit SQL text only. Projection/event fetch helpers below
open Database connections — still Kernel Space
(``check_boundary.py`` treats ``core/runtime/kernel`` as trusted).
"""

from __future__ import annotations

from typing import Any, Iterable

# A defensive upper bound — none of the current call sites need more than a
# few hundred rows. Keeps a runaway ``limit`` from dragging the DB.
MAX_LIMIT = 5000


def safe_limit(limit: int | None, default: int | None = None) -> str:
    """Return a ``LIMIT ?``-free SQL fragment with the integer already inlined.

    All limits flow through here so we can guarantee (a) the value is an int
    and (b) it never exceeds :data:`MAX_LIMIT`. Returns ``""`` when neither
    ``limit`` nor ``default`` is supplied.
    """
    if limit is None:
        if default is None:
            return ""
        limit = default
    n = int(limit)
    if n < 0:
        n = 0
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    return f" LIMIT {n}"


def safe_offset(offset: int | None) -> str:
    """Return an ``OFFSET N`` fragment, or ``""`` when unset/zero."""
    if not offset:
        return ""
    n = int(offset)
    if n < 0:
        n = 0
    if n > MAX_LIMIT * 10:
        n = MAX_LIMIT * 10
    return f" OFFSET {n}"


def safe_order(order: str | None, allowed: dict[str, str], default_key: str) -> str:
    """Return an ``ORDER BY`` fragment validated against ``allowed``.

    ``allowed`` maps a stable public name (e.g. ``"importance_desc"``) to a
    literal SQL fragment. Unknown keys fall back to ``allowed[default_key]``
    rather than being interpolated — this closes the order-by injection
    surface that previously existed wherever ``f"ORDER BY {order_sql}"`` was
    written.
    """
    if order is None:
        order = default_key
    return f" ORDER BY {allowed.get(order, allowed[default_key])}"


def in_clause(values: Iterable[Any]) -> tuple[str, list[Any]]:
    """Build an ``IN (?, ?, ...)`` placeholder list with matching params.

    Returns ``("", [])`` for an empty input so callers can compose it into a
    larger ``WHERE`` without special-casing.
    """
    seq = list(values)
    if not seq:
        return "", []
    placeholders = ",".join("?" * len(seq))
    return f"IN ({placeholders})", seq


def build_where(clauses: list[str]) -> str:
    """Join filter clauses into a ``WHERE ...`` fragment (empty when no clauses).

    Params are owned by the caller; this helper only assembles the clause
    text, so callers retain full control over parameter ordering.
    """
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


# Default batch for sovereignty export — keeps peak memory bounded without
# changing the snapshot wire format (still a full list of row dicts).
EVENT_LOG_EXPORT_BATCH = 2000


def fetch_event_log_dicts(conn: Any, *, batch_size: int = EVENT_LOG_EXPORT_BATCH) -> list[dict[str, Any]]:
    """Read ``event_log`` in seq order via batched ``seq > ?`` cursors.

    Avoids a single ``fetchall()`` of the entire table. Caller owns the
    connection/transaction so ``snapshot()`` can share one read txn.
    """
    out: list[dict[str, Any]] = []
    last_seq = 0
    n = int(batch_size)
    if n < 1:
        n = 1
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    while True:
        rows = conn.execute(
            "SELECT * FROM event_log WHERE seq > ? ORDER BY seq ASC LIMIT ?",
            (last_seq, n),
        ).fetchall()
        if not rows:
            break
        out.extend(dict(r) for r in rows)
        last_seq = int(rows[-1]["seq"])
        if len(rows) < n:
            break
    return out


def fetch_chat_projection_dicts(
    conn: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read conversation/message projections on an open connection."""
    conversations = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM conversations ORDER BY created_at ASC"
        ).fetchall()
    ]
    messages = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM messages ORDER BY created_at ASC"
        ).fetchall()
    ]
    return conversations, messages


def iter_event_log_json_objects(
    conn: Any, *, batch_size: int = EVENT_LOG_EXPORT_BATCH
) -> Iterable[str]:
    """Yield JSON object strings for each event_log row (seq ascending)."""
    import json

    last_seq = 0
    n = int(batch_size)
    if n < 1:
        n = 1
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    while True:
        rows = conn.execute(
            "SELECT * FROM event_log WHERE seq > ? ORDER BY seq ASC LIMIT ?",
            (last_seq, n),
        ).fetchall()
        if not rows:
            return
        for r in rows:
            yield json.dumps(dict(r), ensure_ascii=False)
        last_seq = int(rows[-1]["seq"])
        if len(rows) < n:
            return


def iter_snapshot_document_bytes(
    conn: Any,
    *,
    snapshot_id: str,
    exported_at: str,
    export_format: str,
    batch_size: int = EVENT_LOG_EXPORT_BATCH,
) -> Iterable[bytes]:
    """Stream a lossless snapshot JSON document on an open connection."""
    import json

    def _text() -> Iterable[str]:
        yield "{"
        yield f'"snapshot_id":{json.dumps(snapshot_id)},'
        yield f'"exported_at":{json.dumps(exported_at)},'
        yield f'"format":{json.dumps(export_format)},'
        yield '"event_log":['
        event_count = 0
        first = True
        for obj in iter_event_log_json_objects(conn, batch_size=batch_size):
            if not first:
                yield ","
            first = False
            yield obj
            event_count += 1
        conversations, messages = fetch_chat_projection_dicts(conn)
        goals = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM work_items WHERE work_type = ?",
                ("goal",),
            ).fetchone()["c"]
        )
        memories = int(
            conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
        )
        notifications = int(
            conn.execute("SELECT COUNT(*) AS c FROM notifications").fetchone()["c"]
        )
        yield "],"
        yield '"conversations":'
        yield json.dumps(conversations, ensure_ascii=False)
        yield ',"messages":'
        yield json.dumps(messages, ensure_ascii=False)
        yield ',"counts":'
        yield json.dumps(
            {
                "event_log": event_count,
                "conversations": len(conversations),
                "messages": len(messages),
                "goals": goals,
                "memories": memories,
                "notifications": notifications,
            },
            ensure_ascii=False,
        )
        yield "}"

    for chunk in _text():
        yield chunk.encode("utf-8")


def fetch_event_log_rows(
    db: Any,
    *,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    type: str | None = None,
    types: list[str] | None = None,
    correlation_id: str | None = None,
    since_seq: int = 0,
    since_ts: str | None = None,
    until_ts: str | None = None,
    payload_goal_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    order: str = "asc",
    id: str | None = None,
) -> list[Any]:
    """Read filtered ``event_log`` rows (sqlite Row objects)."""
    clauses = ["seq > ?"]
    params: list[Any] = [since_seq]
    if id is not None:
        clauses.append("id = ?")
        params.append(id)
    if aggregate_type is not None:
        clauses.append("aggregate_type = ?")
        params.append(aggregate_type)
    if aggregate_id is not None:
        clauses.append("aggregate_id = ?")
        params.append(aggregate_id)
    if types:
        placeholders = ",".join("?" * len(types))
        clauses.append(f"type IN ({placeholders})")
        params.extend(types)
    elif type is not None:
        clauses.append("type = ?")
        params.append(type)
    if payload_goal_id is not None:
        clauses.append(
            "(json_extract(payload, '$.goal_id') = ? OR "
            "json_extract(payload, '$.parent_goal_id') = ?)"
        )
        params.append(payload_goal_id)
        params.append(payload_goal_id)
    if correlation_id is not None:
        clauses.append("correlation_id = ?")
        params.append(correlation_id)
    if since_ts is not None:
        clauses.append("ts >= ?")
        params.append(since_ts)
    if until_ts is not None:
        clauses.append("ts <= ?")
        params.append(until_ts)
    where = build_where(clauses)
    order_sql = safe_order(
        order,
        {"asc": "seq ASC", "desc": "seq DESC"},
        default_key="asc",
    )
    limit_sql = safe_limit(limit)
    offset_sql = safe_offset(offset)
    with db.get_db() as conn:
        return list(
            conn.execute(
                f"SELECT * FROM event_log{where}{order_sql}{limit_sql}{offset_sql}",
                params,
            ).fetchall()
        )


# ── Projection reads (extracted from QueryStateMixin) ─────────────────────
# These open Database connections; fragment helpers above stay connection-free.


def query_work_items(db, filters: dict[str, Any]) -> list[dict] | int:
    """Unified query for work_items table.

    Serves all work types (task / action / background / goal).
    """
    item_id = filters.get("id")
    status = filters.get("status")
    status_in = filters.get("status_in")
    work_type = filters.get("work_type")
    parent_goal_id = filters.get("parent_goal_id")
    parent_work_id = filters.get("parent_work_id")
    root_only = filters.get("root_only")
    depends_on_work = filters.get("depends_on_work")
    last_activity_older_than_days = filters.get("last_activity_older_than_days")
    deadline_within_days = filters.get("deadline_within_days")
    updated_since = filters.get("updated_since")
    has_deadline = filters.get("has_deadline")
    limit = filters.get("limit", 50)
    order = filters.get("order", "created_at_asc")
    count_only = filters.get("count_only", False)

    order_clauses = {
        "created_at_asc": "created_at ASC",
        "created_at_desc": "created_at DESC",
        "priority_desc": "priority DESC, created_at ASC",
        "importance_desc": "importance DESC, created_at DESC",
        "importance_urgency_desc": "importance DESC, urgency DESC",
        "last_activity_asc": "last_activity_at ASC",
        "importance_desc_only": "importance DESC",
    }
    order_sql = order_clauses.get(order, order_clauses["created_at_asc"])

    with db.get_db() as conn:
        if item_id:
            if count_only:
                row = conn.execute("SELECT COUNT(*) as c FROM work_items WHERE id = ?", (item_id,)).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        # status_in takes precedence over status when both are present
        # (mirrors _query_goals semantics).
        if status_in is not None:
            placeholders = ",".join("?" * len(status_in))
            clauses.append(f"status IN ({placeholders})")
            params.extend(status_in)
        elif status is not None:
            clauses.append("status = ?")
            params.append(status)
        if work_type is not None:
            clauses.append("work_type = ?")
            params.append(work_type)
        if parent_goal_id is not None:
            clauses.append("parent_goal_id = ?")
            params.append(parent_goal_id)
        if parent_work_id is not None:
            clauses.append("parent_work_id = ?")
            params.append(parent_work_id)
        if root_only:
            clauses.append("parent_work_id IS NULL")
        if depends_on_work is not None:
            clauses.append("dependencies_json LIKE ?")
            params.append(f"%{depends_on_work}%")
        if last_activity_older_than_days is not None:
            clauses.append("last_activity_at < datetime('now', ?)")
            params.append(f"-{int(last_activity_older_than_days)} days")
        if deadline_within_days is not None:
            clauses.append(
                "deadline IS NOT NULL AND deadline BETWEEN datetime('now') AND datetime('now', ?)"
            )
            params.append(f"+{int(deadline_within_days)} days")
        if updated_since is not None:
            clauses.append("updated_at >= ?")
            params.append(updated_since)
        if has_deadline:
            clauses.append("deadline IS NOT NULL")

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(f"SELECT COUNT(*) as c FROM work_items{where}", params).fetchone()
            return int(row["c"])

        params.append(int(limit))
        rows = conn.execute(
            f"SELECT * FROM work_items{where} ORDER BY {order_sql} LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_approvals(db, filters: dict[str, Any]) -> list[dict] | int:
    approval_id = filters.get("id")
    status = filters.get("status")
    limit = filters.get("limit", 50)
    count_only = bool(filters.get("count_only", False))

    with db.get_db() as conn:
        if approval_id:
            if count_only:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM approvals WHERE id = ?",
                    (approval_id,),
                ).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM approvals{where}",
                params,
            ).fetchone()
            return int(row["c"]) if row else 0

        rows = conn.execute(
            f"SELECT * FROM approvals{where} ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return [dict(r) for r in rows]

def query_memories(db, filters: dict[str, Any]) -> list[dict] | int:
    memory_id = filters.get("id")
    category = filters.get("category")
    origin = filters.get("origin")
    claim_status = filters.get("claim_status")
    confidence_gt = filters.get("confidence_gt")
    confidence_lt = filters.get("confidence_lt")
    decay_eligible = filters.get("decay_eligible")
    limit = filters.get("limit", 50)
    count_only = filters.get("count_only", False)

    with db.get_db() as conn:
        if memory_id:
            if count_only:
                row = conn.execute("SELECT COUNT(*) as c FROM memories WHERE id = ?", (memory_id,)).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if origin is not None:
            clauses.append("origin = ?")
            params.append(origin)
        if claim_status is not None:
            clauses.append("claim_status = ?")
            params.append(claim_status)
        if confidence_gt is not None:
            clauses.append("confidence > ?")
            params.append(confidence_gt)
        if confidence_lt is not None:
            clauses.append("confidence < ?")
            params.append(confidence_lt)
        if decay_eligible:
            clauses.append(
                "(decayed_at IS NULL OR decayed_at < datetime('now', '-7 days'))"
            )

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(f"SELECT COUNT(*) as c FROM memories{where}", params).fetchone()
            return int(row["c"])

        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM memories{where} ORDER BY confidence DESC, created_at DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_notifications(db, filters: dict[str, Any]) -> list[dict] | int:
    notification_id = filters.get("id")
    notif_type = filters.get("type")
    title = filters.get("title")
    unread_only = filters.get("unread_only")
    created_on_date = filters.get("created_on_date")
    related_id = filters.get("related_id")
    notification_type = filters.get("notification_type")
    dedup_key = filters.get("dedup_key")
    limit = filters.get("limit", 50)
    order = filters.get("order", "created_at_desc")
    count_only = bool(filters.get("count_only", False))

    order_clauses = {
        "created_at_desc": "created_at DESC",
        "created_at_asc": "created_at ASC",
    }
    order_sql = order_clauses.get(order, order_clauses["created_at_desc"])

    with db.get_db() as conn:
        if notification_id:
            if count_only:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM notifications WHERE id = ?",
                    (notification_id,),
                ).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ?", (notification_id,)
            ).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        if notif_type is not None:
            clauses.append("type = ?")
            params.append(notif_type)
        if title is not None:
            clauses.append("title = ?")
            params.append(title)
        if unread_only:
            clauses.append("read = 0")
        if created_on_date is not None:
            clauses.append("date(created_at) = date(?)")
            params.append(created_on_date)
        if related_id is not None:
            clauses.append("related_id = ?")
            params.append(related_id)
        if notification_type is not None:
            clauses.append("notification_type = ?")
            params.append(notification_type)
        if dedup_key is not None:
            clauses.append("dedup_key = ?")
            params.append(dedup_key)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM notifications{where}",
                params,
            ).fetchone()
            return int(row["c"]) if row else 0

        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM notifications{where} ORDER BY {order_sql} LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_conversations(db, filters: dict[str, Any]) -> list[dict]:
    conv_id = filters.get("id")
    limit = filters.get("limit", 50)
    order = filters.get("order", "created_at_desc")

    order_sql = "updated_at DESC" if order == "created_at_desc" else "created_at ASC"
    with db.get_db() as conn:
        if conv_id:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            return [dict(row)] if row else []
        rows = conn.execute(
            f"SELECT * FROM conversations ORDER BY {order_sql} LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]

def query_messages(db, filters: dict[str, Any]) -> list[dict]:
    message_id = filters.get("id")
    conversation_id = filters.get("conversation_id")
    limit = filters.get("limit", 20)
    order = filters.get("order", "created_at_desc")

    order_clauses = {
        "created_at_desc": "created_at DESC",
        "created_at_asc": "created_at ASC",
    }
    order_sql = order_clauses.get(order, order_clauses["created_at_desc"])

    with db.get_db() as conn:
        if message_id:
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            return [dict(row)] if row else []

        if not conversation_id:
            return []

        rows = conn.execute(
            f"""SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY {order_sql}
                LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]

def query_inbox_emails(db, filters: dict[str, Any]) -> list[dict] | int:
    email_id = filters.get("id")
    status = filters.get("status")
    status_not = filters.get("status_not")
    category = filters.get("category")
    digested = filters.get("digested")
    notified = filters.get("notified")
    search = filters.get("search")
    limit = filters.get("limit", 20)
    order = filters.get("order", "date_desc")
    count_only = bool(filters.get("count_only", False))

    order_clauses = {
        "date_desc": "COALESCE(received_at, created_at) DESC",
        "date_asc": "COALESCE(received_at, created_at) ASC",
        "created_at_desc": "created_at DESC",
        "importance_desc": "importance DESC, COALESCE(received_at, created_at) DESC",
    }
    order_sql = order_clauses.get(order, order_clauses["date_desc"])

    with db.get_db() as conn:
        if email_id:
            if count_only:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM inbox_emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute(
                "SELECT * FROM inbox_emails WHERE id = ?", (email_id,)
            ).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("COALESCE(status, 'pending') = ?")
            params.append(status)
        if status_not is not None:
            clauses.append("status != ?")
            params.append(status_not)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if digested is not None:
            clauses.append("COALESCE(digested, 0) = ?")
            params.append(1 if digested else 0)
        if notified is not None:
            clauses.append("COALESCE(notified, 0) = ?")
            params.append(1 if notified else 0)
        if search:
            clauses.append(
                "(subject LIKE ? OR sender LIKE ? OR preview LIKE ?)"
            )
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM inbox_emails{where}",
                params,
            ).fetchone()
            return int(row["c"]) if row else 0

        params.append(limit)
        rows = conn.execute(
            f'SELECT * FROM inbox_emails{where} ORDER BY {order_sql} LIMIT ?',
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_timer_events(db, filters: dict[str, Any]) -> list[dict] | int:
    timer_id = filters.get("id")
    status = filters.get("status")
    fire_at_lt = filters.get("fire_at_lt")
    limit = filters.get("limit", 50)
    count_only = bool(filters.get("count_only", False))

    with db.get_db() as conn:
        if timer_id:
            if count_only:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM timer_events WHERE id = ?",
                    (timer_id,),
                ).fetchone()
                return int(row["c"]) if row else 0
            row = conn.execute(
                "SELECT * FROM timer_events WHERE id = ?",
                (timer_id,),
            ).fetchone()
            return [dict(row)] if row else []

        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if fire_at_lt is not None:
            clauses.append("fire_at <= ? AND fire_at != ''")
            params.append(fire_at_lt)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM timer_events{where}",
                params,
            ).fetchone()
            return int(row["c"]) if row else 0

        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM timer_events{where} ORDER BY fire_at ASC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_policy_events(db, filters: dict[str, Any]) -> list[dict] | int:
    capability = filters.get("capability")
    status = filters.get("status")
    limit = filters.get("limit", 200)
    count_only = bool(filters.get("count_only", False))

    with db.get_db() as conn:
        clauses: list[str] = []
        params: list[Any] = []
        if capability is not None:
            clauses.append("capability = ?")
            params.append(capability)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        if count_only:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM policy_events{where}",
                params,
            ).fetchone()
            return int(row["c"]) if row else 0

        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM policy_events{where} ORDER BY capability ASC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def query_user_profile(db, filters: dict[str, Any]) -> list[dict]:
    category = filters.get("id")
    # ``limit`` is optional: omit for a full category listing (small table).
    limit = filters.get("limit")
    with db.get_db() as conn:
        if category:
            row = conn.execute(
                "SELECT * FROM user_profile WHERE category = ?", (category,)
            ).fetchone()
            return [dict(row)] if row else []
        if limit is None:
            rows = conn.execute(
                "SELECT * FROM user_profile ORDER BY category"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_profile ORDER BY category LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]

def query_tool_calls(db, filters: dict[str, Any]) -> list[dict]:
    from app.store.telemetry_queries import select_telemetry_rows
    return select_telemetry_rows(db, "tool_calls", filters, name_col="tool_name")

def query_llm_calls(db, filters: dict[str, Any]) -> list[dict]:
    from app.store.telemetry_queries import select_telemetry_rows
    return select_telemetry_rows(db, "llm_calls", filters)


def aggregate_llm_calls_summary(db, filters: dict[str, Any]) -> dict:
    from app.store.telemetry_queries import aggregate_llm_summary

    return aggregate_llm_summary(db, days=filters.get("since_days", 7))


def aggregate_llm_calls_by_model(db, filters: dict[str, Any]) -> list[dict]:
    from app.store.telemetry_queries import aggregate_llm_by_model

    return aggregate_llm_by_model(db, days=filters.get("since_days", 7))


def aggregate_tool_calls_summary(db, filters: dict[str, Any]) -> list[dict]:
    from app.store.telemetry_queries import aggregate_tool_summary

    return aggregate_tool_summary(db, days=filters.get("since_days", 7))


def aggregate_call_failure_rates(db, filters: dict[str, Any]) -> dict:
    from app.store.telemetry_queries import aggregate_call_failure_rates as _agg

    return _agg(db, days=int(filters.get("since_days", 1) or 1))


def aggregate_memory_stats(db, filters: dict[str, Any] | None = None) -> dict:
    """Memory totals / categories / recent_7d via SQL COUNT (no row cap)."""
    del filters  # reserved for future filters
    from app.store.memory_queries import aggregate_memory_stats as _agg

    return _agg(db)

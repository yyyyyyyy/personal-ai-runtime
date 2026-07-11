"""Typed query-construction helpers for Kernel read paths.

Centralises the patterns that were previously hand-written across the Kernel
mixins (``WHERE`` clause assembly, ``LIMIT``/``ORDER BY`` injection,
``IN (...)`` placeholders). Goals:

- No ad-hoc f-strings in call sites — every fragment is built here.
- ``int(limit)`` coercion lives in exactly one place, with a sane ceiling.
- ``ORDER BY`` clauses are validated against an allowlist dict so callers
  cannot inject arbitrary SQL via the ``order`` parameter — unknown keys
  fall back to the default rather than being interpolated.

This module emits only SQLite fragments; it never opens a connection.
``check_boundary.py`` treats ``core/runtime/kernel`` as Kernel Space, so
introducing SQL here does not violate the governance boundary.
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

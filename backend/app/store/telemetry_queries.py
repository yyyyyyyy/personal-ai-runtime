"""Governed telemetry projection readers (llm_calls / tool_calls).

Kept in the store layer so Kernel QueryStateMixin stays thin — SELECT on
governed tables is allowed here (see check_boundary._is_store_layer).
"""

from __future__ import annotations

from typing import Any


def select_telemetry_rows(
    db: Any,
    table: str,
    filters: dict[str, Any],
    *,
    name_col: str | None = None,
) -> list[dict]:
    """Read llm_calls or tool_calls with optional since_days / tool_name / offset."""
    if table not in ("llm_calls", "tool_calls"):
        raise ValueError(f"unsupported telemetry table: {table!r}")
    limit = filters.get("limit", 5000)
    offset = int(filters.get("offset", 0) or 0)
    clauses: list[str] = []
    params: list[Any] = []
    if name_col and filters.get("tool_name"):
        clauses.append(f"{name_col} = ?")
        params.append(filters["tool_name"])
    since_days = filters.get("since_days")
    if since_days is not None:
        clauses.append("created_at >= datetime('now', ?)")
        params.append(f"-{int(since_days)} days")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([int(limit), offset])
    with db.get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table}{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

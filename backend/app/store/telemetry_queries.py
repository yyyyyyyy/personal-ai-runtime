"""Governed telemetry projection readers (llm_calls / tool_calls).

Kept in the store layer so Kernel QueryStateMixin stays thin — SELECT on
governed tables is allowed here (see check_boundary._is_store_layer).
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from app.store.database import Database


class TelemetryRow(TypedDict):
    """Schema for telemetry result rows."""
    id: str
    created_at: str
    success: int
    latency_ms: float
    # Other fields are dynamic depending on table (llm_calls vs tool_calls)


def select_telemetry_rows(
    db: Database,
    table: str,
    filters: dict[str, Any],
    *,
    name_col: str | None = None,
) -> list[dict]:
    """
    Read llm_calls or tool_calls with optional since_days / name / success / offset.
    
    Args:
        db: Database instance.
        table: Table name ('llm_calls' or 'tool_calls').
        filters: Dictionary containing:
            - limit (int, default 5000)
            - offset (int, default 0)
            - since_days (int, optional)
            - name (str, optional, matches tool_name or model)
            - success (int, optional, 0 or 1)
        name_col: Explicit column name for name filtering (e.g. 'tool_name' or 'model').
    """
    if table not in ("llm_calls", "tool_calls"):
        raise ValueError(f"unsupported telemetry table: {table!r}")

    # 1. Normalize and validate basic pagination
    try:
        limit = min(max(int(filters.get("limit", 5000)), 1), 10000)
        offset = max(int(filters.get("offset", 0) or 0), 0)
    except (ValueError, TypeError):
        limit, offset = 5000, 0

    clauses: list[str] = []
    params: list[Any] = []

    # 2. Add filters
    # Name filter (tool_name or model)
    name_val = filters.get("name") or filters.get("tool_name")
    if name_val and (name_col or table == "llm_calls"):
        actual_name_col = name_col or "model"
        clauses.append(f"{actual_name_col} = ?")
        params.append(name_val)

    # Success filter
    success = filters.get("success")
    if success is not None:
        clauses.append("success = ?")
        params.append(1 if success else 0)

    # Time filter
    since_days = filters.get("since_days")
    if since_days is not None:
        try:
            days_int = int(since_days)
            clauses.append("created_at >= datetime('now', ?)")
            params.append(f"-{days_int} days")
        except ValueError:
            pass

    # 3. Build and execute query
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM {table}{where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with db.get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]

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


def created_at_since_sql(
    since_days: int | None,
    *,
    column: str = "created_at",
) -> tuple[str | None, list[Any]]:
    """Return ``(predicate, params)`` comparing ISO/SQLite timestamps safely.

    Event timestamps are ISO-8601 (``…T…+00:00``); SQLite ``datetime('now')``
    uses a space separator. Normalize both sides to ``YYYY-MM-DD HH:MM:SS``.
    """
    if since_days is None:
        return None, []
    try:
        days_int = int(since_days)
    except (TypeError, ValueError):
        return None, []
    # substr(...,1,19) drops fractional seconds and timezone suffix;
    # replace T→space aligns with SQLite datetime() text form.
    normalized = f"datetime(replace(substr({column}, 1, 19), 'T', ' '))"
    return f"{normalized} >= datetime('now', ?)", [f"-{days_int} days"]


def _since_clause(since_days: int | None) -> tuple[str, list[Any]]:
    pred, params = created_at_since_sql(since_days)
    if pred is None:
        return "", []
    return f" WHERE {pred}", params


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

    # Optional purpose filter (chat / memory_extract / …)
    purpose = filters.get("purpose")
    if purpose:
        clauses.append("purpose = ?")
        params.append(str(purpose))

    # Time filter (ISO-safe)
    since_pred, since_params = created_at_since_sql(filters.get("since_days"))
    if since_pred is not None:
        clauses.append(since_pred)
        params.extend(since_params)

    # 3. Build and execute query
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM {table}{where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with db.get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def aggregate_llm_summary(db: Database, *, days: int | None = 7) -> dict[str, Any]:
    """Full-window LLM totals via SQL (no row cap)."""
    where, params = _since_clause(days)
    with db.get_db() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                COALESCE(SUM(cost), 0) AS total_cost,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(SUM(CASE WHEN COALESCE(success, 1) = 0 THEN 1 ELSE 0 END), 0)
                    AS failed_calls
            FROM llm_calls{where}
            """,
            params,
        ).fetchone()
    total = int(row["total_calls"] or 0)
    return {
        "total_calls": total,
        "total_prompt_tokens": int(row["total_prompt_tokens"] or 0),
        "total_completion_tokens": int(row["total_completion_tokens"] or 0),
        "total_cost": float(row["total_cost"] or 0),
        "avg_latency_ms": float(row["avg_latency_ms"] or 0),
        "failed_calls": int(row["failed_calls"] or 0),
        "sample_size": total,
        "capped": False,
    }


def aggregate_llm_by_model(db: Database, *, days: int | None = 7) -> list[dict[str, Any]]:
    """LLM totals grouped by provider + model (no row cap)."""
    where, params = _since_clause(days)
    with db.get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(provider, '') AS provider,
                COALESCE(model, '') AS model,
                COUNT(*) AS total_calls,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(prompt_tokens), 0) + COALESCE(SUM(completion_tokens), 0)
                    AS total_tokens,
                COALESCE(SUM(cost), 0) AS cost,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(SUM(CASE WHEN COALESCE(success, 1) = 0 THEN 1 ELSE 0 END), 0)
                    AS failed_calls
            FROM llm_calls{where}
            GROUP BY provider, model
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()
    return [
        {
            "provider": str(r["provider"]),
            "model": str(r["model"]),
            "total_calls": int(r["total_calls"] or 0),
            "prompt_tokens": int(r["prompt_tokens"] or 0),
            "completion_tokens": int(r["completion_tokens"] or 0),
            "total_tokens": int(r["total_tokens"] or 0),
            "cost": float(r["cost"] or 0),
            "avg_latency_ms": float(r["avg_latency_ms"] or 0),
            "failed_calls": int(r["failed_calls"] or 0),
            "capped": False,
        }
        for r in rows
    ]


def aggregate_tool_summary(db: Database, *, days: int | None = 7) -> list[dict[str, Any]]:
    """Tool-call totals grouped by tool_name (no row cap)."""
    where, params = _since_clause(days)
    with db.get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(tool_name, '') AS tool_name,
                COUNT(*) AS total_calls,
                COALESCE(SUM(CASE WHEN COALESCE(success, 1) = 0 THEN 1 ELSE 0 END), 0)
                    AS failed_calls,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
            FROM tool_calls{where}
            GROUP BY tool_name
            ORDER BY total_calls DESC
            """,
            params,
        ).fetchall()
    return [
        {
            "tool_name": str(r["tool_name"]),
            "total_calls": int(r["total_calls"] or 0),
            "failed_calls": int(r["failed_calls"] or 0),
            "avg_latency_ms": float(r["avg_latency_ms"] or 0),
            "capped": False,
        }
        for r in rows
    ]


def aggregate_call_failure_rates(db: Database, *, days: int = 1) -> dict[str, Any]:
    """24h-style failure rates for LLM and tool calls."""
    where, params = _since_clause(days)
    with db.get_db() as conn:
        llm = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN COALESCE(success, 1) = 0 THEN 1 ELSE 0 END), 0)
                    AS failed
            FROM llm_calls{where}
            """,
            params,
        ).fetchone()
        tool = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN COALESCE(success, 1) = 0 THEN 1 ELSE 0 END), 0)
                    AS failed
            FROM tool_calls{where}
            """,
            params,
        ).fetchone()
    llm_total = int(llm["total"] or 0)
    tool_total = int(tool["total"] or 0)
    llm_fail = int(llm["failed"] or 0)
    tool_fail = int(tool["failed"] or 0)
    return {
        "llm_total": llm_total,
        "llm_failed": llm_fail,
        "llm_failure_rate": round(llm_fail / llm_total, 4) if llm_total else 0.0,
        "tool_total": tool_total,
        "tool_failed": tool_fail,
        "tool_failure_rate": round(tool_fail / tool_total, 4) if tool_total else 0.0,
        "sample_size_llm": llm_total,
        "sample_size_tool": tool_total,
        "capped": False,
    }

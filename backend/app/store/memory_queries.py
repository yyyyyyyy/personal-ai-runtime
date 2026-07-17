"""Governed memories projection aggregations.

Kept in the store layer so Kernel QueryStateMixin stays thin — SELECT on
governed tables is allowed here (see check_boundary._is_store_layer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.store.telemetry_queries import created_at_since_sql

if TYPE_CHECKING:
    from app.store.database import Database


def aggregate_memory_stats(db: Database) -> dict[str, Any]:
    """Memory totals / categories / recent_7d via SQL COUNT (no row cap)."""
    recent_pred, recent_params = created_at_since_sql(7)
    with db.get_db() as conn:
        total = int(conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"])
        recent = int(
            conn.execute(
                f"SELECT COUNT(*) AS c FROM memories WHERE {recent_pred}",
                recent_params,
            ).fetchone()["c"]
        )
        cat_rows = conn.execute(
            "SELECT COALESCE(NULLIF(TRIM(category), ''), 'unknown') AS category, "
            "COUNT(*) AS c FROM memories GROUP BY category"
        ).fetchall()
    return {
        "total_memories": total,
        "categories": {str(r["category"]): int(r["c"]) for r in cat_rows},
        "recent_7d": recent,
        "sample_size": total,
        "capped": False,
    }

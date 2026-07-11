"""Telemetry — observability views over LLM calls, tool calls, and system health.

v0.11.0: removed the legacy ``record_llm_call`` / ``record_tool_call`` direct
INSERT methods and their ``LLMCallRecord`` / ``ToolCallRecord`` data classes.
Telemetry writes now flow exclusively through the Kernel as
``LLMCallRecorded`` / ``CapabilityInvoked`` events (see
``brain_telemetry.record_llm_call`` and ``projectors_telemetry``). This module
retains only the read-side aggregations consumed by the Telemetry API.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel_instance import kernel
from app.store.database import db


def _parse_utc_datetime(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class Telemetry:
    """Read-only aggregations over the governed telemetry projections."""

    def get_llm_summary(self, days: int = 7) -> dict:
        """Get cost/token/latency summary for recent LLM calls."""
        rows = kernel.query_state("llm_calls", limit=5000)
        cutoff = datetime.now(UTC) - timedelta(days=days)
        total = failed = 0
        total_prompt = total_completion = total_cost = 0
        latencies: list[float] = []
        for r in rows:
            created = r.get("created_at")
            if not created:
                continue
            dt = _parse_utc_datetime(str(created))
            if dt is None or dt < cutoff:
                continue
            total += 1
            total_prompt += r.get("prompt_tokens", 0) or 0
            total_completion += r.get("completion_tokens", 0) or 0
            total_cost += r.get("cost", 0) or 0
            lat = r.get("latency_ms")
            if lat is not None:
                latencies.append(float(lat))
            if not r.get("success", 1):
                failed += 1
        return {
            "total_calls": total,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cost": total_cost,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "failed_calls": failed,
        }

    def get_llm_summary_by_model(self, days: int = 7) -> list[dict]:
        """Get token/cost breakdown grouped by provider and model."""
        with db.get_db() as conn:
            rows = conn.execute(
                """SELECT
                    provider,
                    model,
                    COUNT(*) as total_calls,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(prompt_tokens) + SUM(completion_tokens) as total_tokens,
                    SUM(cost) as cost,
                    AVG(latency_ms) as avg_latency_ms,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls
                   FROM llm_calls
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY provider, model
                   ORDER BY total_tokens DESC""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tool_summary(self, days: int = 7) -> list[dict]:
        """Get tool call success rate and latency summary."""
        with db.get_db() as conn:
            rows = conn.execute(
                """SELECT
                    tool_name,
                    COUNT(*) as total_calls,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls,
                    AVG(latency_ms) as avg_latency_ms
                   FROM tool_calls
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY tool_name""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_llm_calls(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_calls ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tool_calls(self, limit: int = 50, tool_name: str | None = None) -> list[dict]:
        with db.get_db() as conn:
            if tool_name:
                rows = conn.execute(
                    "SELECT * FROM tool_calls WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
                    (tool_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tool_calls ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_memory_stats(self) -> dict:
        """Get memory system stats: total count, categories, recent additions."""
        memories = kernel.query_state("memories", limit=5000)
        cutoff = datetime.now(UTC) - timedelta(days=7)
        recent_count = 0
        for mem in memories:
            created = mem.get("created_at")
            if not created:
                continue
            created_dt = _parse_utc_datetime(created)
            if created_dt and created_dt >= cutoff:
                recent_count += 1
        return {
            "total_memories": len(memories),
            "categories": dict(Counter(m.get("category") or "unknown" for m in memories)),
            "recent_7d": recent_count,
        }

    def get_health(self) -> dict:
        """Get runtime health snapshot."""
        queue_len = sum(
            len(kernel.query_state("work_items", status=status, limit=5000))
            for status in ("pending", "running", "blocked")
        )
        cutoff_24h = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        llm_rows = kernel.query_state("llm_calls", limit=5000)
        tool_rows = kernel.query_state("tool_calls", limit=5000)
        llm_count = llm_fail = tool_count = tool_fail = 0
        for r in llm_rows:
            if r.get("created_at", "") >= cutoff_24h:
                llm_count += 1
                if not r.get("success", 1):
                    llm_fail += 1
        for r in tool_rows:
            if r.get("created_at", "") >= cutoff_24h:
                tool_count += 1
                if not r.get("success", 1):
                    tool_fail += 1
        return {
            "task_queue_length": queue_len,
            "llm_failure_rate_24h": round(llm_fail / llm_count, 4) if llm_count else 0,
            "tool_failure_rate_24h": round(tool_fail / tool_count, 4) if tool_count else 0,
            **self._memory_index_repair_counts(),
        }

    def _memory_index_repair_counts(self) -> dict[str, int]:
        with db.get_db() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM memory_index_repairs WHERE status = 'pending'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM memory_index_repairs WHERE status = 'failed_permanent'"
            ).fetchone()[0]
        return {
            "memory_index_repairs_pending": int(pending),
            "memory_index_repairs_failed_permanent": int(failed),
        }

    def get_memory_index_repairs(self, status: str | None = None) -> dict:
        """List durable memory index repair rows and aggregate counts."""
        counts = self._memory_index_repair_counts()
        query = (
            "SELECT id, aggregate_id, event_type, event_seq, error, retry_count, "
            "status, created_at, last_retry_at "
            "FROM memory_index_repairs"
        )
        params: tuple = ()
        if status and status != "all":
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY id DESC LIMIT 200"
        with db.get_db() as conn:
            rows = conn.execute(query, params).fetchall()
        items = [
            {
                "id": row["id"],
                "aggregate_id": row["aggregate_id"],
                "event_type": row["event_type"],
                "event_seq": row["event_seq"],
                "error": row["error"],
                "retry_count": row["retry_count"],
                "status": row["status"],
                "created_at": row["created_at"],
                "last_retry_at": row["last_retry_at"],
            }
            for row in rows
        ]
        return {
            "pending": counts["memory_index_repairs_pending"],
            "failed_permanent": counts["memory_index_repairs_failed_permanent"],
            "items": items,
        }

    def retry_memory_index_repair(self, repair_id: int) -> dict:
        """Reset a failed_permanent repair row so RuntimeLoop can drain it again."""
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT id, status FROM memory_index_repairs WHERE id = ?",
                (repair_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "not_found"}
            if row["status"] != "failed_permanent":
                return {"ok": False, "error": "not_retryable", "status": row["status"]}
            conn.execute(
                "UPDATE memory_index_repairs "
                "SET status = 'pending', retry_count = 0, error = NULL, last_retry_at = NULL "
                "WHERE id = ?",
                (repair_id,),
            )
        return {"ok": True, "id": repair_id, "status": "pending"}


from app.core.runtime.runtime_container import _LazyProxy, runtime  # noqa: E402

telemetry = _LazyProxy(lambda: runtime.telemetry)


def reset_telemetry() -> None:
    """Rebuild the telemetry singleton (test isolation)."""
    runtime._telemetry = None

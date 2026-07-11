"""Telemetry — observability views over LLM calls, tool calls, and system health.

v0.11.0: removed the legacy ``record_llm_call`` / ``record_tool_call`` direct
INSERT methods and their ``LLMCallRecord`` / ``ToolCallRecord`` data classes.
Telemetry writes now flow exclusively through the Kernel as
``LLMCallRecorded`` / ``CapabilityInvoked`` events (see
``brain_telemetry.record_llm_call`` and ``projectors_telemetry``).

v0.12.0: governed-table *reads* also go through ``kernel.query_state``
(``llm_calls`` / ``tool_calls`` / ``memories`` / ``work_items``). Direct SQL
is reserved for APP_STORAGE (``memory_index_repairs``).
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from app.core.runtime import read_ports
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
        rows = read_ports.query_llm_calls(days=days, limit=5000)
        total = failed = 0
        total_prompt = total_completion = total_cost = 0
        latencies: list[float] = []
        for r in rows:
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
        rows = read_ports.query_llm_calls(days=days, limit=5000)
        groups: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = (str(r.get("provider") or ""), str(r.get("model") or ""))
            g = groups.get(key)
            if g is None:
                g = {
                    "provider": key[0],
                    "model": key[1],
                    "total_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "latency_sum": 0.0,
                    "latency_n": 0,
                    "failed_calls": 0,
                }
                groups[key] = g
            g["total_calls"] += 1
            prompt = r.get("prompt_tokens", 0) or 0
            completion = r.get("completion_tokens", 0) or 0
            g["prompt_tokens"] += prompt
            g["completion_tokens"] += completion
            g["total_tokens"] += prompt + completion
            g["cost"] += float(r.get("cost", 0) or 0)
            lat = r.get("latency_ms")
            if lat is not None:
                g["latency_sum"] += float(lat)
                g["latency_n"] += 1
            if not r.get("success", 1):
                g["failed_calls"] += 1

        result = []
        for g in groups.values():
            result.append({
                "provider": g["provider"],
                "model": g["model"],
                "total_calls": g["total_calls"],
                "prompt_tokens": g["prompt_tokens"],
                "completion_tokens": g["completion_tokens"],
                "total_tokens": g["total_tokens"],
                "cost": g["cost"],
                "avg_latency_ms": (g["latency_sum"] / g["latency_n"]) if g["latency_n"] else 0,
                "failed_calls": g["failed_calls"],
            })
        result.sort(key=lambda x: x["total_tokens"], reverse=True)
        return result

    def get_tool_summary(self, days: int = 7) -> list[dict]:
        """Get tool call success rate and latency summary."""
        rows = read_ports.query_tool_calls(days=days, limit=5000)
        groups: dict[str, dict] = defaultdict(lambda: {
            "total_calls": 0,
            "failed_calls": 0,
            "latency_sum": 0.0,
            "latency_n": 0,
        })
        for r in rows:
            name = str(r.get("tool_name") or "")
            g = groups[name]
            g["total_calls"] += 1
            if not r.get("success", 1):
                g["failed_calls"] += 1
            lat = r.get("latency_ms")
            if lat is not None:
                g["latency_sum"] += float(lat)
                g["latency_n"] += 1
        return [
            {
                "tool_name": name,
                "total_calls": g["total_calls"],
                "failed_calls": g["failed_calls"],
                "avg_latency_ms": (g["latency_sum"] / g["latency_n"]) if g["latency_n"] else 0,
            }
            for name, g in groups.items()
        ]

    def get_llm_calls(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return read_ports.query_llm_calls(limit=limit, offset=offset)

    def get_tool_calls(self, limit: int = 50, tool_name: str | None = None) -> list[dict]:
        return read_ports.query_tool_calls(tool_name=tool_name, limit=limit)

    def get_memory_stats(self) -> dict:
        """Get memory system stats: total count, categories, recent additions."""
        memories = read_ports.query_memories(limit=5000)
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
            len(read_ports.query_work_items(status=status, limit=5000))
            for status in ("pending", "running", "blocked")
        )
        llm_rows = read_ports.query_llm_calls(days=1, limit=5000)
        tool_rows = read_ports.query_tool_calls(days=1, limit=5000)
        llm_count = len(llm_rows)
        llm_fail = sum(1 for r in llm_rows if not r.get("success", 1))
        tool_count = len(tool_rows)
        tool_fail = sum(1 for r in tool_rows if not r.get("success", 1))
        return {
            "task_queue_length": queue_len,
            "llm_failure_rate_24h": round(llm_fail / llm_count, 4) if llm_count else 0,
            "tool_failure_rate_24h": round(tool_fail / tool_count, 4) if tool_count else 0,
            **self._memory_index_repair_counts(),
        }

    def _memory_index_repair_counts(self) -> dict[str, int]:
        # APP_STORAGE — direct access is allowed.
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

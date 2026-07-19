"""Telemetry — observability views over LLM calls, tool calls, and system health.

Telemetry writes flow exclusively through the Kernel as ``LLMCallRecorded`` /
``CapabilityInvoked`` events (see ``brain_telemetry.record_llm_call`` and
``projectors_governance``).

Governed-table reads go through ``kernel.query_state`` / ``aggregate_state``
(``llm_calls`` / ``tool_calls`` / ``memories`` / ``work_items``). Direct SQL is
reserved for APP_STORAGE (``memory_index_repairs``).
"""

import logging

from app.core.runtime import read_ports
from app.store.database import db

logger = logging.getLogger(__name__)


class Telemetry:
    """Read-only aggregations over the governed telemetry projections."""

    def get_llm_summary(self, days: int = 7) -> dict:
        """Get cost/token/latency summary for recent LLM calls."""
        return read_ports.summarize_llm_calls(days=days)

    def get_llm_summary_by_model(self, days: int = 7) -> list[dict]:
        """Get token/cost breakdown grouped by provider and model."""
        return read_ports.summarize_llm_calls_by_model(days=days)

    def get_tool_summary(self, days: int = 7) -> list[dict]:
        """Get tool call success rate and latency summary."""
        return read_ports.summarize_tool_calls(days=days)

    def get_llm_calls(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return read_ports.query_llm_calls(limit=limit, offset=offset)

    def get_tool_calls(self, limit: int = 50, tool_name: str | None = None) -> list[dict]:
        return read_ports.query_tool_calls(tool_name=tool_name, limit=limit)

    def get_memory_stats(self) -> dict:
        """Get memory system stats: total count, categories, recent additions."""
        return read_ports.summarize_memory_stats()

    def get_health(self) -> dict:
        """Get runtime health snapshot."""
        from app.core.runtime.read_ports._common import kernel

        active_work_items = 0
        for status in ("pending", "running", "blocked"):
            try:
                active_work_items += int(
                    kernel().count_state("work_items", status=status)
                )
            except Exception:
                logger.warning(
                    "telemetry health: count_state(work_items, status=%r) failed",
                    status,
                    exc_info=True,
                )

        rates = read_ports.summarize_call_failure_rates(days=1)
        return {
            # Legacy key kept for API compatibility.
            "task_queue_length": active_work_items,
            "active_work_items": active_work_items,
            "llm_failure_rate_24h": rates.get("llm_failure_rate", 0),
            "tool_failure_rate_24h": rates.get("tool_failure_rate", 0),
            "sample_size_llm_24h": rates.get("sample_size_llm", 0),
            "sample_size_tool_24h": rates.get("sample_size_tool", 0),
            "capped": bool(rates.get("capped", False)),
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

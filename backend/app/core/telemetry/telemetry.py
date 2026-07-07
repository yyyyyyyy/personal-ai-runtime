"""Telemetry — observability data collection for LLM calls, tool calls, and system health.

Records every LLM inference and tool invocation for cost tracking, debugging, and dashboards.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
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


@dataclass
class LLMCallRecord:
    """Complete record of a single LLM API call."""
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0
    cost: float = 0
    success: bool = True
    error_message: str | None = None


@dataclass
class ToolCallRecord:
    """Complete record of a single tool invocation."""
    tool_name: str
    success: bool = True
    latency_ms: float = 0
    error_message: str | None = None


class Telemetry:
    """Records LLM and tool call data for observability."""

    def record_llm_call(self, record: LLMCallRecord) -> str:
        call_id = str(uuid.uuid4())
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO llm_calls (id, provider, model, prompt_tokens, completion_tokens,
                   latency_ms, cost, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    call_id,
                    record.provider,
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.latency_ms,
                    record.cost,
                    1 if record.success else 0,
                    record.error_message,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return call_id

    def record_tool_call(self, record: ToolCallRecord) -> str:
        call_id = str(uuid.uuid4())
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO tool_calls (id, tool_name, success, latency_ms, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    call_id,
                    record.tool_name,
                    1 if record.success else 0,
                    record.latency_ms,
                    record.error_message,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return call_id

    def get_llm_summary(self, days: int = 7) -> dict:
        """Get cost/token/latency summary for recent LLM calls."""
        with db.get_db() as conn:
            row = conn.execute(
                """SELECT
                    COUNT(*) as total_calls,
                    SUM(prompt_tokens) as total_prompt_tokens,
                    SUM(completion_tokens) as total_completion_tokens,
                    SUM(cost) as total_cost,
                    AVG(latency_ms) as avg_latency_ms,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls
                   FROM llm_calls
                   WHERE created_at >= datetime('now', ?)""",
                (f"-{days} days",),
            ).fetchone()
        return dict(row) if row else {}

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
        with db.get_db() as conn:
            llm_fail_rate = conn.execute(
                """SELECT
                    CASE WHEN COUNT(*) > 0
                    THEN CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
                    ELSE 0 END as rate
                   FROM llm_calls
                   WHERE created_at >= datetime('now', '-1 days')"""
            ).fetchone()["rate"]
            tool_fail_rate = conn.execute(
                """SELECT
                    CASE WHEN COUNT(*) > 0
                    THEN CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
                    ELSE 0 END as rate
                   FROM tool_calls
                   WHERE created_at >= datetime('now', '-1 days')"""
            ).fetchone()["rate"]
        return {
            "task_queue_length": queue_len,
            "llm_failure_rate_24h": round(llm_fail_rate, 4),
            "tool_failure_rate_24h": round(tool_fail_rate, 4),
        }


telemetry = Telemetry()


def reset_telemetry() -> None:
    """Rebuild the telemetry singleton (test isolation)."""
    global telemetry
    telemetry = Telemetry()

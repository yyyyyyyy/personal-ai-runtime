"""Telemetry — observability data collection for LLM calls, tool calls, and system health.

Records every LLM inference and tool invocation for cost tracking, debugging, and dashboards.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.store.database import db


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
                    datetime.utcnow().isoformat(),
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
                    datetime.utcnow().isoformat(),
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

    def get_tool_summary(self, days: int = 7) -> dict:
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
        with db.get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            by_category = conn.execute(
                "SELECT category, COUNT(*) as count FROM memories GROUP BY category"
            ).fetchall()
            recent_count = conn.execute(
                "SELECT COUNT(*) as c FROM memories WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()["c"]
        return {
            "total_memories": total,
            "categories": {r["category"]: r["count"] for r in by_category},
            "recent_7d": recent_count,
        }

    def get_health(self) -> dict:
        """Get runtime health snapshot."""
        with db.get_db() as conn:
            queue_len = conn.execute(
                "SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending', 'running', 'blocked')"
            ).fetchone()["c"]
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

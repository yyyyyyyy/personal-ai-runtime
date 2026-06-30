"""Critic Agent — audits executor outputs, rejects unauthorized operations.

Enhanced with failure pattern detection for self-healing (v0.2.0).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

FORBIDDEN_PATTERNS = ["rm -rf", "DROP TABLE", "DELETE FROM", "shutdown", "format"]

MAX_CONSECUTIVE_FAILURES = 3
MAX_SAME_TOOL_FAILURES = 2
FAILURE_WINDOW_SECONDS = 120


class FailureRecord:
    def __init__(self, tool_name: str, error: str, task_id: str = ""):
        self.tool_name = tool_name
        self.error = error
        self.timestamp = datetime.now(UTC)
        self.task_id = task_id


class CriticAgent:
    def __init__(self, rejection_threshold: float = 0.3):
        self.rejection_threshold = rejection_threshold
        self.total_checks = 0
        self.total_rejections = 0
        self.failure_history: list[FailureRecord] = []

    def audit_step(self, tool_name: str, params: dict, result: str | None = None, task_id: str = "") -> bool:
        self.total_checks += 1

        params_str = str(params).lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.lower() in params_str:
                self.total_rejections += 1
                self._record_failure(tool_name, f"Forbidden: {pattern}", task_id)
                return False

        if result and isinstance(result, str):
            try:
                parsed = json.loads(result)
                if parsed.get("status") == "error":
                    self._record_failure(tool_name, parsed.get("error", "unknown"), task_id)
                    return False
            except (json.JSONDecodeError, TypeError):
                pass

        # Write-class tool safety: sourced from taint.WRITE_CLASS_TOOLS for
        # consistency with INV-8 (taint escalation). No hardcoded duplication.
        from app.core.runtime.taint import WRITE_CLASS_TOOLS
        dangerous_tools = WRITE_CLASS_TOOLS
        if tool_name in dangerous_tools and not params.get("_approved", False):
            self.total_rejections += 1
            return False

        return True

    def _record_failure(self, tool_name: str, error: str, task_id: str) -> None:
        self.failure_history.append(FailureRecord(tool_name, error, task_id))
        cutoff = datetime.now(UTC).timestamp() - FAILURE_WINDOW_SECONDS
        self.failure_history = [f for f in self.failure_history if f.timestamp.timestamp() > cutoff]

    def rejection_rate(self) -> float:
        return self.total_rejections / self.total_checks if self.total_checks > 0 else 0.0

    def should_replan(self, task_id: str = "") -> bool:
        if self.rejection_rate() > self.rejection_threshold:
            logger.info("Replan: rejection rate %.2f > %.2f", self.rejection_rate(), self.rejection_threshold)
            return True
        return self._detect_failure_pattern(task_id)

    def _detect_failure_pattern(self, task_id: str = "") -> bool:
        failures = [f for f in self.failure_history if not task_id or f.task_id == task_id]
        if len(failures) < MAX_CONSECUTIVE_FAILURES:
            return False
        logger.warning("Replan: %d consecutive failures in window", len(failures))
        return True

    def get_failing_tools(self, task_id: str = "") -> set[str]:
        failures = [f for f in self.failure_history if not task_id or f.task_id == task_id]
        tool_counts: dict[str, int] = {}
        for f in failures:
            tool_counts[f.tool_name] = tool_counts.get(f.tool_name, 0) + 1
        return {t for t, c in tool_counts.items() if c >= MAX_SAME_TOOL_FAILURES}

    def reset_for_task(self, task_id: str = "") -> None:
        self.failure_history = [f for f in self.failure_history if f.task_id != task_id] if task_id else []


critic = CriticAgent()

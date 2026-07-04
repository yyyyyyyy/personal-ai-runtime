"""Execution Context — runtime snapshot for Execution-Aware Context Policy.

Provides the Policy with a read-only view of recent runtime activity:
    - Which fragments were recently injected
    - Which tools were recently executed
    - What events recently occurred
    - Whether any failures happened recently
    - Which goals appear stagnant

This snapshot is built by ExecutionContextProvider from the Kernel's
event log and state projections. It is read-only — Policy observes it
but never mutates it.

Architecture:
    ExecutionContextProvider.build(...)
        ↓
    ExecutionContext (frozen, read-only snapshot)
        ↓
    DefaultContextPolicy.evaluate(request, candidates)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.runtime.kernel.constants import (
    EVENT_CAPABILITY_FAILED,
    EVENT_CAPABILITY_INVOKED,
    EVENT_EXECUTION_FAILED,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Governance Execution Context (read-only snapshot) ────────────────────


@dataclass(frozen=True)
class GovernanceExecutionContext:
    """Read-only runtime snapshot for context policy evaluation.

    Built by ContextPipeline before each policy evaluation.
    Consumed by context-aware policies.
    """

    recent_fragment_ids: tuple[str, ...] = field(default_factory=tuple)
    recent_tool_names: tuple[str, ...] = field(default_factory=tuple)
    recent_event_types: tuple[str, ...] = field(default_factory=tuple)
    recent_failures: tuple[str, ...] = field(default_factory=tuple)
    stagnant_goal_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_failures(self) -> bool:
        return bool(self.recent_failures)

    @property
    def has_stagnant_goals(self) -> bool:
        return bool(self.stagnant_goal_ids)


_DEFAULT_SNAPSHOT = GovernanceExecutionContext()

# ── Mapping: tool name → fragment tags to suppress ─────────────────────

_TOOL_FRAGMENT_TAG_MAP: dict[str, str] = {
    "list_calendar_events": "calendar",
    "create_calendar_event": "calendar",
    "get_calendar_upcoming": "calendar",
    "search_email": "mail",
    "get_recent_emails": "mail",
    "send_email": "mail",
    "add_memory": "memory",
    "goal_update": "goals",
    "goal_create": "goals",
    "task_create": "planning",
    "query_knowledge": "knowledge",
    "search_documents": "knowledge",
}

# ── Failure event types (any of these count as "recent failures") ──────

_FAILURE_EVENT_TYPES: frozenset[str] = frozenset({
    EVENT_CAPABILITY_FAILED,
    EVENT_EXECUTION_FAILED,
    "TaskFailed",  # legacy event type, kept for backward compat
})

# ── Default lookback windows ─────────────────────────────────────────────

_DEFAULT_EVENT_LOOKBACK_DAYS = 14
_DEFAULT_EVENT_LIMIT = 50
_DEFAULT_STAGNATION_DAYS = 7


class ExecutionContextProvider:
    """Builds a GovernanceExecutionContext snapshot from Kernel runtime state.

    Responsible for translating raw event log + state projection data
    into a clean, policy-friendly read-only snapshot. This is the ONLY
    component authorized to read the Kernel for context policy purposes.

    Fragments, Assembler, and Pipeline are explicitly forbidden from
    reading Event Log or Tool Results directly.
    """

    def __init__(
        self,
        *,
        event_lookback_days: int = _DEFAULT_EVENT_LOOKBACK_DAYS,
        event_limit: int = _DEFAULT_EVENT_LIMIT,
        stagnation_days: int = _DEFAULT_STAGNATION_DAYS,
    ):
        self._event_lookback_days = event_lookback_days
        self._event_limit = event_limit
        self._stagnation_days = stagnation_days

    async def build(
        self,
        *,
        conversation_id: str = "",
        execution_id: str = "",
    ) -> GovernanceExecutionContext:
        """Build a GovernanceExecutionContext from current runtime state.

        Returns a default (empty) snapshot when the Kernel / DB is
        unavailable, which preserves backward compatibility for tests
        and environments without a live event store.
        """
        try:
            from app.core.runtime.kernel_instance import kernel
        except Exception:
            logger.debug("Kernel not available; returning empty execution context")
            return _DEFAULT_SNAPSHOT

        recent_tool_names: list[str] = []
        recent_event_types: list[str] = []
        recent_failures: list[str] = []
        stagnant_goal_ids: list[str] = []

        # 1. Read recent events from event log
        since_ts = (datetime.now(UTC) - timedelta(days=self._event_lookback_days)).isoformat()
        try:
            events = kernel.read_events(
                since_ts=since_ts,
                limit=self._event_limit,
                order="desc",
            )
        except Exception:
            logger.debug("Failed to read events from kernel; using empty snapshot", exc_info=True)
            events = []

        for evt in events:
            event_type = evt.type
            recent_event_types.append(event_type)

            # Track tool invocations
            if event_type == EVENT_CAPABILITY_INVOKED:
                tool_name = evt.payload.get("name", "")
                if tool_name:
                    recent_tool_names.append(tool_name)

            # Track failures
            if event_type in _FAILURE_EVENT_TYPES:
                detail = f"{event_type}:{evt.aggregate_id}"
                recent_failures.append(detail)

        # 2. Check for stagnant goals (no activity > threshold)
        try:
            goals = kernel.query_state(
                "goals",
                status_in=("active", "in_progress"),
                last_activity_older_than_days=self._stagnation_days,
                limit=20,
                order="last_activity_asc",
            )
            for g in goals:
                gid = g.get("id", "")
                if gid:
                    stagnant_goal_ids.append(gid)
        except Exception:
            logger.debug("Failed to query goals for stagnation", exc_info=True)

        return GovernanceExecutionContext(
            recent_fragment_ids=(),  # filled by Pipeline after each compilation
            recent_tool_names=tuple(dedup_preserve_order(recent_tool_names)),
            recent_event_types=tuple(dedup_preserve_order(recent_event_types)),
            recent_failures=tuple(dedup_preserve_order(recent_failures)),
            stagnant_goal_ids=tuple(stagnant_goal_ids),
        )


def dedup_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate a list while preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ── Tool-to-fragment-tag lookup ───────────────────────────────────────

def tool_names_to_fragment_tags(tool_names: tuple[str, ...]) -> set[str]:
    """Map recently executed tool names to fragment domain tags.

    Used by the policy to suppress fragments whose domain overlaps
    with recently executed tools.
    """
    tags: set[str] = set()
    for name in tool_names:
        tag = _TOOL_FRAGMENT_TAG_MAP.get(name)
        if tag:
            tags.add(tag)
    return tags

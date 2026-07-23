# mypy: disable-error-code="attr-defined"
"""Kernel Query State Mixin — read-only projection queries.

SQL executors live in ``query_builder`` (not counted toward God Object LOC).
This mixin keeps the ``query_state`` selector router and thin ABI wrappers.
"""

from __future__ import annotations

from typing import Any

from . import query_builder as qb

# Selectors that support efficient SQL COUNT via ``count_state``.
COUNT_STATE_SELECTORS: frozenset[str] = frozenset({
    "work_items",
    "memories",
    "approvals",
    "notifications",
    "inbox_emails",
    "timer_events",
    "policy_events",
})


class QueryStateMixin:  # type: ignore[attr-defined]  # mixed into Kernel which provides _db
    """Read layer: query_state and projection table accessors."""

    def query_state(self, selector: str, **filters: Any) -> list[dict]:
        """Read a projection. Prefer ``read_ports`` helpers for new call sites."""
        if selector == "work_items":  # unified task + action + goal
            return self._as_rows(self._query_work_items(filters))
        if selector == "approvals":
            return self._as_rows(self._query_approvals(filters))
        if selector == "memories":
            return self._as_rows(self._query_memories(filters))
        if selector == "notifications":
            return self._as_rows(self._query_notifications(filters))
        if selector == "policy_events":
            return self._as_rows(self._query_policy_events(filters))
        if selector == "conversations":
            return self._as_rows(self._query_conversations(filters))
        if selector == "messages":
            return self._as_rows(self._query_messages(filters))
        if selector == "inbox_emails":
            return self._as_rows(self._query_inbox_emails(filters))
        if selector == "timer_events":
            return self._as_rows(self._query_timer_events(filters))
        if selector == "user_profile":
            return self._as_rows(self._query_user_profile(filters))
        if selector == "tool_calls":
            return self._as_rows(self._query_tool_calls(filters))
        if selector == "llm_calls":
            return self._as_rows(self._query_llm_calls(filters))
        raise ValueError(f"Unknown state selector: {selector!r}")

    @staticmethod
    def _as_rows(result: list[dict] | int) -> list[dict]:
        if isinstance(result, int):
            raise TypeError("count_only result passed to query_state")
        return result

    @staticmethod
    def supports_count_state(selector: str) -> bool:
        """Return True when ``count_state`` has a real COUNT path for selector."""
        return selector in COUNT_STATE_SELECTORS

    def count_state(self, selector: str, **filters: Any) -> int:
        """Count projection rows efficiently without loading them into memory."""
        filters["count_only"] = True
        dispatch = {
            "work_items": self._query_work_items,
            "memories": self._query_memories,
            "approvals": self._query_approvals,
            "notifications": self._query_notifications,
            "inbox_emails": self._query_inbox_emails,
            "timer_events": self._query_timer_events,
            "policy_events": self._query_policy_events,
        }
        query = dispatch.get(selector)
        if query is None:
            raise ValueError(f"count_state not implemented for selector: {selector!r}")
        result = query(filters)
        if not isinstance(result, int):
            raise TypeError(f"count_only query for {selector!r} did not return int")
        return result

    def aggregate_state(self, selector: str, **filters: Any) -> Any:
        """SQL aggregations over governed projections (no silent row caps)."""
        if selector == "llm_calls_summary":
            return qb.aggregate_llm_calls_summary(self._db, filters)
        if selector == "llm_calls_by_model":
            return qb.aggregate_llm_calls_by_model(self._db, filters)
        if selector == "tool_calls_summary":
            return qb.aggregate_tool_calls_summary(self._db, filters)
        if selector == "call_failure_rates":
            return qb.aggregate_call_failure_rates(self._db, filters)
        if selector == "memory_stats":
            return qb.aggregate_memory_stats(self._db, filters)
        raise ValueError(f"Unknown aggregate selector: {selector!r}")

    def _query_work_items(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_work_items(self._db, filters)

    def _query_approvals(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_approvals(self._db, filters)

    def _query_memories(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_memories(self._db, filters)

    def _query_notifications(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_notifications(self._db, filters)

    def list_capability_definitions(self) -> list[dict]:
        """Thin forward to harness — prefer ``mcp_hub.get_tool_defs_for_llm``."""
        from app.core.harness.mcp_hub import mcp_hub

        return mcp_hub.get_tool_defs_for_llm()

    def recall_memory(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall via injected MemoryIndexPort (no global vector bypass)."""
        port = getattr(self, "_memory_index", None)
        if port is None:
            return []
        return port.search_memories(query, n_results=k)

    def recall_knowledge(self, query: str, k: int = 5) -> list[dict]:
        """Knowledge recall via injected MemoryIndexPort."""
        port = getattr(self, "_memory_index", None)
        if port is None:
            return []
        return port.search_knowledge(query, n_results=k)

    def _query_conversations(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_conversations(self._db, filters)

    def _query_messages(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_messages(self._db, filters)

    def _query_inbox_emails(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_inbox_emails(self._db, filters)

    def _query_policy_events(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_policy_events(self._db, filters)

    def _query_timer_events(self, filters: dict[str, Any]) -> list[dict] | int:
        return qb.query_timer_events(self._db, filters)

    def _query_user_profile(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_user_profile(self._db, filters)

    def _query_tool_calls(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_tool_calls(self._db, filters)

    def _query_llm_calls(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_llm_calls(self._db, filters)

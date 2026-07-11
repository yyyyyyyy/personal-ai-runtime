# mypy: disable-error-code="attr-defined"
"""Kernel Query State Mixin — read-only projection queries.

SQL executors live in ``query_builder`` (not counted toward God Object LOC).
This mixin keeps the ``query_state`` selector router and thin ABI wrappers.
"""

from __future__ import annotations

from typing import Any

from . import query_builder as qb


class QueryStateMixin:  # type: ignore[attr-defined]  # mixed into Kernel which provides _db
    """Read layer: query_state and projection table accessors."""

    def query_state(self, selector: str, **filters: Any) -> list[dict]:
        """Read a projection. Prefer ``read_ports`` helpers for new call sites."""
        if selector == "work_items":  # unified task + action + goal
            return self._query_work_items(filters)
        if selector == "approvals":
            return self._query_approvals(filters)
        if selector == "memories":
            return self._query_memories(filters)
        if selector == "notifications":
            return self._query_notifications(filters)
        if selector == "policy_events":
            return self._query_policy_events(filters)
        if selector == "conversations":
            return self._query_conversations(filters)
        if selector == "messages":
            return self._query_messages(filters)
        if selector == "inbox_emails":
            return self._query_inbox_emails(filters)
        if selector == "tool_calls":
            return self._query_tool_calls(filters)
        if selector == "llm_calls":
            return self._query_llm_calls(filters)
        raise ValueError(f"Unknown state selector: {selector!r}")

    def _query_work_items(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_work_items(self._db, filters)

    def _query_approvals(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_approvals(self._db, filters)

    def _query_memories(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_memories(self._db, filters)

    def _query_notifications(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_notifications(self._db, filters)

    def list_capability_definitions(self) -> list[dict]:
        """Read-only capability metadata for LLM tool schemas (User Space ABI)."""
        from app.core.harness.mcp_hub import mcp_hub

        return mcp_hub.get_tool_defs_for_llm()

    def recall_memory(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from derived memories (projected from MemoryDerived events)."""
        from app.store.vector import vector_store

        return vector_store.search_memories(query, n_results=k)

    def recall_knowledge(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from knowledge base documents."""
        from app.store.vector import vector_store

        return vector_store.search_knowledge(query, n_results=k)

    def _query_conversations(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_conversations(self._db, filters)

    def _query_messages(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_messages(self._db, filters)

    def _query_inbox_emails(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_inbox_emails(self._db, filters)

    def _query_policy_events(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_policy_events(self._db, filters)

    def _query_tool_calls(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_tool_calls(self._db, filters)

    def _query_llm_calls(self, filters: dict[str, Any]) -> list[dict]:
        return qb.query_llm_calls(self._db, filters)

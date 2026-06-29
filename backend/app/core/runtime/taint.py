"""Untrusted content taint tracking for Prompt Injection mitigation.

When external content (inbox, web fetch, browser) enters the agent context,
subsequent write-class capability invocations in the same correlation chain
MUST require user approval.

Tool names MUST match mcp_hub registrations and capability_policy.json.
"""

from __future__ import annotations

import contextvars
from typing import Any

# Builtin MCP tools that ingest untrusted external content (see mcp_hub).
_BUILTIN_EXTERNAL_INGESTION_TOOLS = frozenset({
    "check_inbox",
    "read_inbox_email",
    "web_search",
    "fetch_url",
    "search_and_extract",
    "open_web_page",
})

_EXTERNAL_INGESTION_DYNAMIC: set[str] = set()

EXTERNAL_INGESTION_TOOLS = _BUILTIN_EXTERNAL_INGESTION_TOOLS


def register_external_ingestion_tool(name: str) -> None:
    _EXTERNAL_INGESTION_DYNAMIC.add(name)


def clear_external_ingestion_tools() -> None:
    _EXTERNAL_INGESTION_DYNAMIC.clear()


_EXTERNAL_WRITE_DYNAMIC: set[str] = set()

# Registered MCP tools in capability_policy.json "needs_user" — mutate host or exfiltrate.
WRITE_CLASS_TOOLS = frozenset({
    "apply_patch",
    "write_file",
    "add_calendar_event",
    "send_email",
    "shell_exec",
    "telegram_send",
    "computer_click",
    "computer_type",
    "computer_key",
})


_taint_marks: contextvars.ContextVar[dict[str, dict[str, Any]] | None] = contextvars.ContextVar(
    "taint_marks",
    default=None,
)


class TaintRegistry:
    """Async/task-local taint marks keyed by correlation_id."""

    def _store(self) -> dict[str, dict[str, Any]]:
        store = _taint_marks.get()
        if store is None:
            store = {}
            _taint_marks.set(store)
        return store

    def mark(self, correlation_id: str | None, *, source: str, reason: str = "") -> None:
        if not correlation_id:
            return
        self._store()[correlation_id] = {
            "source": source,
            "reason": reason or source,
        }

    def is_tainted(self, correlation_id: str | None) -> bool:
        if not correlation_id:
            return False
        return correlation_id in self._store()

    def clear(self, correlation_id: str | None) -> None:
        if correlation_id:
            self._store().pop(correlation_id, None)

    def clear_all(self) -> None:
        self._store().clear()


taint_registry = TaintRegistry()


def is_external_ingestion_tool(name: str) -> bool:
    return name in _BUILTIN_EXTERNAL_INGESTION_TOOLS or name in _EXTERNAL_INGESTION_DYNAMIC


def register_external_write_tool(name: str) -> None:
    _EXTERNAL_WRITE_DYNAMIC.add(name)


def clear_external_write_tools() -> None:
    _EXTERNAL_WRITE_DYNAMIC.clear()


def is_write_class_tool(name: str) -> bool:
    return name in WRITE_CLASS_TOOLS or name in _EXTERNAL_WRITE_DYNAMIC

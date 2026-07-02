"""Untrusted content taint tracking for Prompt Injection mitigation.

When external content (inbox, web fetch, browser) enters the agent context,
subsequent write-class capability invocations in the same correlation chain
MUST require user approval.

Tool names MUST match mcp_hub registrations and capability_policy.json.

v0.2.1: Taint marks moved from contextvars.ContextVar to an instance-level dict
with TTL-based expiry. ContextVar was async-task-local and broke under
asyncio.gather fan-out in the Scheduler, silently dropping taint across tasks
that share the same correlation_id.
"""

from __future__ import annotations

import time
from typing import Any

# TTL for taint marks in seconds (5 minutes).
# After this duration, the mark is considered expired and cleaned up on next access.
_TAINT_TTL_SECONDS = 300

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


class TaintRegistry:
    """Instance-level taint marks keyed by correlation_id with TTL expiry.

    Uses a plain dict instead of contextvars.ContextVar so that taint
    propagates across asyncio task boundaries (e.g. asyncio.gather in the
    Scheduler). Each mark carries a timestamp; entries older than
    _TAINT_TTL_SECONDS are silently evicted on access via _expire().
    """

    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}

    def _expire(self) -> None:
        """Remove stale taint marks older than _TAINT_TTL_SECONDS."""
        now = time.monotonic()
        stale = [cid for cid, m in self._store.items()
                 if now - m.get("_ts", 0) > _TAINT_TTL_SECONDS]
        for cid in stale:
            self._store.pop(cid, None)

    def mark(self, correlation_id: str | None, *, source: str, reason: str = "") -> None:
        if not correlation_id:
            return
        self._store[correlation_id] = {
            "source": source,
            "reason": reason or source,
            "_ts": time.monotonic(),
        }

    def is_tainted(self, correlation_id: str | None) -> bool:
        if not correlation_id:
            return False
        self._expire()
        return correlation_id in self._store

    def clear(self, correlation_id: str | None) -> None:
        if correlation_id:
            self._store.pop(correlation_id, None)

    def clear_all(self) -> None:
        self._store.clear()


from app.core.runtime.runtime_container import _LazyProxy, runtime
taint_registry = _LazyProxy(lambda: runtime.taint_registry)


def is_external_ingestion_tool(name: str) -> bool:
    return name in _BUILTIN_EXTERNAL_INGESTION_TOOLS or name in _EXTERNAL_INGESTION_DYNAMIC


def register_external_write_tool(name: str) -> None:
    _EXTERNAL_WRITE_DYNAMIC.add(name)


def clear_external_write_tools() -> None:
    _EXTERNAL_WRITE_DYNAMIC.clear()


def reset_external_tools() -> None:
    """Clear all dynamic external tool registrations — for test isolation."""
    _EXTERNAL_INGESTION_DYNAMIC.clear()
    _EXTERNAL_WRITE_DYNAMIC.clear()
    taint_registry.clear_all()


def is_write_class_tool(name: str) -> bool:
    return name in WRITE_CLASS_TOOLS or name in _EXTERNAL_WRITE_DYNAMIC

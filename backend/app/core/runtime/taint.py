"""Untrusted content taint tracking for Prompt Injection mitigation.

When external content (inbox, web fetch, browser) enters the agent context,
subsequent write-class capability invocations in the same correlation chain
MUST require user approval.

Tool classification is loaded from capability_policy.json (single source of
truth): ``needs_user`` → write-class, ``external_ingestion`` → taint sources.

v0.2.1: Taint marks moved from contextvars.ContextVar to an instance-level dict
with TTL-based expiry. ContextVar was async-task-local and broke under
asyncio.gather fan-out in the Scheduler, silently dropping taint across tasks
that share the same correlation_id.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.runtime.runtime_container import _LazyProxy, runtime

# TTL for taint marks in seconds (5 minutes).
# After this duration, the mark is considered expired and cleaned up on next access.
_TAINT_TTL_SECONDS = 300

_POLICY_PATH = Path(__file__).resolve().parents[3] / "capability_policy.json"


def _load_capability_policy() -> dict[str, Any]:
    if not _POLICY_PATH.is_file():
        return {}
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


_policy = _load_capability_policy()

# Write-class tools: mutate host or exfiltrate — sourced from needs_user.
WRITE_CLASS_TOOLS = frozenset(_policy.get("needs_user", []))

# Builtin MCP tools that ingest untrusted external content.
_BUILTIN_EXTERNAL_INGESTION_TOOLS = frozenset(_policy.get("external_ingestion", []))
EXTERNAL_INGESTION_TOOLS = _BUILTIN_EXTERNAL_INGESTION_TOOLS

_EXTERNAL_INGESTION_DYNAMIC: set[str] = set()
_EXTERNAL_WRITE_DYNAMIC: set[str] = set()


def register_external_ingestion_tool(name: str) -> None:
    _EXTERNAL_INGESTION_DYNAMIC.add(name)


def clear_external_ingestion_tools() -> None:
    _EXTERNAL_INGESTION_DYNAMIC.clear()


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


if TYPE_CHECKING:
    taint_registry: TaintRegistry
else:
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

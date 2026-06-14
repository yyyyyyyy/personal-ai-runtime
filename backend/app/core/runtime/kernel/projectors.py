"""Projectors — turn the immutable Event Log into mutable State (materialized views).

Per docs/RUNTIME_SPEC.md: State is a *projection* of Events, never written directly.
Handlers are split across projectors_core, projectors_chat, and projectors_aux.
"""

from . import projectors_aux, projectors_chat, projectors_core  # noqa: F401 — register handlers
from .projectors_registry import _OWNED_TABLES, apply, owned_tables

__all__ = ["apply", "owned_tables", "_OWNED_TABLES"]

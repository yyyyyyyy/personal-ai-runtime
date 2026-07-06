"""Projectors — turn the immutable Event Log into mutable State (materialized views).

Per docs/RUNTIME_SPEC.md: State is a *projection* of Events, never written directly.
Handlers are split across projectors_core (goals, memory, notifications, work_items,
user_profile), projectors_chat, projectors_background, projectors_execution,
projectors_governance, and projectors_timer.
"""

from . import (  # noqa: F401 — register handlers
    projectors_background,
    projectors_chat,
    projectors_core,
    projectors_execution,
    projectors_governance,
    projectors_inbox,
    projectors_timer,
)
from .projectors_registry import _OWNED_TABLES, apply, owned_tables

__all__ = ["apply", "owned_tables", "_OWNED_TABLES"]

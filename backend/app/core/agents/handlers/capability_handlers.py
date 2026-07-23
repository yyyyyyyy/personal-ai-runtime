"""Capability execution handlers — compat barrel.

Canonical modules live in ``app.core.runtime.handlers``.
Background work uses ``on_execute_requested`` (INV-W5).
"""

from app.core.runtime.handlers.approve_handlers import on_approve_requested
from app.core.runtime.handlers.execute_handlers import on_execute_requested
from app.core.runtime.handlers.inbox_poll_handlers import on_inbox_poll_requested

__all__ = [
    "on_approve_requested",
    "on_execute_requested",
    "on_inbox_poll_requested",
]

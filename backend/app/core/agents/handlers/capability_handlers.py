"""Capability execution handlers — compat barrel.

Canonical modules live in ``app.core.runtime.handlers``.
"""

from app.core.runtime.handlers.approve_handlers import on_approve_requested
from app.core.runtime.handlers.background_task_handlers import on_bg_task_requested
from app.core.runtime.handlers.execute_handlers import on_execute_requested
from app.core.runtime.handlers.inbox_poll_handlers import on_inbox_poll_requested

__all__ = [
    "on_approve_requested",
    "on_bg_task_requested",
    "on_execute_requested",
    "on_inbox_poll_requested",
]

"""Runtime capability / orchestration handlers.

Non-chat handlers (approve, execute, inbox poll) live here because they are
Scheduler orchestration, not Brain reasoning. Background work uses the same
``ExecuteRequested`` handler as user-triggered execute (INV-W5).

Chat handlers remain under ``app.core.agents.handlers``.
Importing this package registers ``@subscribe`` handlers.
"""

from app.core.runtime.handlers import (
    approve_handlers,  # noqa: F401
    execute_handlers,  # noqa: F401
    inbox_poll_handlers,  # noqa: F401
)

__all__ = [
    "approve_handlers",
    "execute_handlers",
    "inbox_poll_handlers",
]

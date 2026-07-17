"""Runtime capability / orchestration handlers.

Non-chat handlers (approve, execute, background task, inbox poll) live here
because they are Scheduler orchestration, not Brain reasoning.

Chat handlers remain under ``app.core.agents.handlers``.
Importing this package registers ``@subscribe`` handlers.
"""

from app.core.runtime.handlers import (
    approve_handlers,  # noqa: F401
    background_task_handlers,  # noqa: F401
    execute_handlers,  # noqa: F401
    inbox_poll_handlers,  # noqa: F401
)

__all__ = [
    "approve_handlers",
    "background_task_handlers",
    "execute_handlers",
    "inbox_poll_handlers",
]

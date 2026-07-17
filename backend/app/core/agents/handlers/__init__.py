"""Agent chat handlers + registration entry for Personal AI Runtime.

Chat / ChatCompleted / Timer stay here (agent-facing).
Capability orchestration handlers live in ``app.core.runtime.handlers``;
importing this package also registers them (single bootstrap entry).
"""

# Import handler modules to trigger @subscribe decorator registration.
from app.core.runtime import handlers as _runtime_handlers  # noqa: E402, F401

from . import (
    chat_completed_handlers,  # noqa: E402, F401
    chat_handler,  # noqa: E402, F401
    timer_trigger_handler,  # noqa: E402, F401
)

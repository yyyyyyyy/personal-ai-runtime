"""Chat handler registration for the Personal AI Runtime.

Handlers are registered via @subscribe("EventType") decorators.
handler_registry dispatches by event type only.
"""

# Import handler modules to trigger @subscribe decorator registration.
from . import (
    capability_handlers,  # noqa: E402, F401
    chat_completed_handlers,  # noqa: E402, F401
    chat_handler,  # noqa: E402, F401
    timer_trigger_handler,  # noqa: E402, F401
)

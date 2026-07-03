"""MVP Agent definitions — handler registration for the Personal AI Runtime.

Handlers are registered via @subscribe("EventType") decorators.
No AgentDefinition or SubscriptionRule needed — handler_registry dispatches
by event type only.

v0.4.0: AgentDefinition and SubscriptionRule removed.
"""

# Import handlers to register @subscribe decorators
from . import (
    bypass_handlers,  # noqa: E402, F401
    chat_completed_handlers,  # noqa: E402, F401
    chat_handler,  # noqa: E402, F401
    timer_trigger_handler,  # noqa: E402, F401
)

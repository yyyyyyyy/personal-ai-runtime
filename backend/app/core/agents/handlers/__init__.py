"""Agent chat handlers + registration entry for Personal AI Runtime.

Chat / ChatCompleted / Timer stay here (agent-facing).
Capability orchestration handlers live in ``app.core.runtime.handlers``;
importing this package also registers them (single bootstrap entry).
"""

# Product inbox binds its poll applier into RuntimeContainer (R1).
# Runtime handlers register @subscribe; relative chat handlers follow.
import app.product.inbox as _product_inbox  # noqa: F401
from app.core.runtime import handlers as _runtime_handlers  # noqa: F401

from . import (
    chat_completed_handlers,  # noqa: F401
    chat_handler,  # noqa: F401
    timer_trigger_handler,  # noqa: F401
)

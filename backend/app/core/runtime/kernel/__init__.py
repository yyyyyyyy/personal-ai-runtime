"""Personal AI Runtime — Kernel.

The boundary of the Runtime. User Space (agents, workflows, APIs, UI) talks to
the system exclusively through `Kernel`; only the Kernel touches storage.

See docs/RUNTIME_SPEC.md (v1.0 FROZEN) for the object model, boundary, and ABI.
"""

from .event import Event
from .kernel import Kernel

__all__ = ["Event", "Kernel"]

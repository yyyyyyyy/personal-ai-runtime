"""ExecutionContext — minimal runtime context passed to handlers (ADR-0007 Step 5/8).

Replaces AgentInstance as the handler's first argument. Exposes only what
a handler needs: identity (for event emission and logging), emit(), and
the Principal (for future capability authorization, Step 9).

Execution Ownership: execution_id binds this handler run to
the Execution aggregate. Handlers that call invoke_capability MUST pass
this execution_id so CapabilityGateway can attribute every capability
invocation to a specific Execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .execution import Principal

if TYPE_CHECKING:
    from .kernel.event import Event
    from .kernel.kernel import Kernel


@dataclass
class ExecutionContext:
    """Minimal runtime context passed to handlers.

    Carries only what a handler needs to execute: identity (for event
    emission and logging), the kernel reference (for emit), and the
    Principal (typed identity for capability authorization).
    """

    instance_id: str
    actor: str
    correlation_id: str
    _kernel: "Kernel"
    principal: Principal = field(default_factory=Principal.system)

    # Execution Ownership: the Execution aggregate_id that owns
    # this handler run. Every capability invocation inside this handler
    # MUST be attributable to this Execution.
    execution_id: str = ""

    def emit(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
        caused_by: str | None = None,
    ) -> "Event":
        """Emit an event through the Kernel with this context's actor."""
        return self._kernel.emit_event(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            actor=self.actor,
            caused_by=caused_by,
            correlation_id=self.correlation_id or None,
        )

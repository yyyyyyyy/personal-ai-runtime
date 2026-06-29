"""AgentInstance — the runtime container for a single Agent.

Each AgentInstance wraps a reference to the shared Kernel and manages:
  - Independent state (projections filtered by agent_id)
  - Event Stream View — a filtered window into the ONE global Event Log
    (NOT a separate log; all events live in the same append-only event_log,
    isolated by actor = 'agent:{instance_id}')
  - Independent checkpoint (per-agent projection_checkpoints)

There is only ONE Event Log.  Agents do not own their own logs — they
own a filtered subscription (Event Stream View) into the global log.

State is Projector First — there is no in-memory Reducer.  Agent state
lives in projection tables, materialised from the global Event Log by
the Kernel's projector pipeline.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .agent_definition import AgentDefinition

if TYPE_CHECKING:
    from .kernel.event import Event
    from .kernel.kernel import Kernel

logger = logging.getLogger(__name__)


@dataclass
class AgentInstance:
    """Lightweight runtime container for an Agent.

    All state reads/writes go through the shared Kernel. The instance_id
    serves as the isolation key: all events emitted by this instance carry
    'agent:{instance_id}' as the actor, and checkpoint queries filter by
    instance_id.
    """

    definition: AgentDefinition
    kernel: "Kernel"
    instance_id: str = field(default_factory=lambda: f"aginst_{uuid.uuid4().hex[:12]}")
    status: str = "spawning"
    spawned_at: str | None = None
    last_active_at: str | None = None
    correlation_id: str | None = None

    # --- lifecycle -------------------------------------------------------

    def actor_id(self) -> str:
        """The actor string used in Kernel emit_event calls."""
        return f"agent:{self.instance_id}"

    async def start(self) -> None:
        """Transition to running. Registers subscriptions on the AgentBus."""
        from datetime import UTC, datetime
        self.status = "running"
        self.spawned_at = datetime.now(UTC).isoformat()
        self.last_active_at = self.spawned_at
        logger.info(
            "AgentInstance %s (%s) started", self.instance_id, self.definition.agent_id
        )

    async def stop(self, reason: str = "completed") -> None:
        """Gracefully terminate the instance."""
        self.status = "terminated"
        logger.info(
            "AgentInstance %s stopped: %s", self.instance_id, reason
        )

    async def pause(self) -> None:
        """Pause processing but keep state."""
        self.status = "paused"

    async def resume(self) -> None:
        """Resume processing from paused state."""
        from datetime import UTC, datetime
        self.status = "running"
        self.last_active_at = datetime.now(UTC).isoformat()

    # --- event operations ------------------------------------------------

    async def emit(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
        caused_by: str | None = None,
    ) -> "Event":
        """Emit an event through the Kernel with this agent as the actor.

        All events emitted here are automatically tagged with the agent's
        instance_id as actor, ensuring isolation in the shared Event Log.
        """
        from datetime import UTC, datetime
        self.last_active_at = datetime.now(UTC).isoformat()
        return self.kernel.emit_event(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            actor=self.actor_id(),
            caused_by=caused_by,
            correlation_id=self.correlation_id,
        )

    async def read_events(
        self,
        aggregate_type: str | None = None,
        since_seq: int = 0,
    ) -> list["Event"]:
        """Read events where this agent is the actor."""
        events = self.kernel.read_events(
            aggregate_type=aggregate_type,
            since_seq=since_seq,
        )
        actor_prefix = self.actor_id()
        return [e for e in events if e.actor == actor_prefix]

    # --- state -----------------------------------------------------------

    async def get_state(self, aggregate_type: str) -> list[dict[str, Any]]:
        """Query projection state for this agent's aggregates."""
        return self.kernel.query_state(aggregate_type)

    # --- checkpoint ------------------------------------------------------

    async def get_checkpoint_seq(self, aggregate_type: str) -> int:
        """Return the last checkpoint sequence for this agent/aggregate pair."""
        return self.kernel._checkpoint_seq(
            agent_id=self.instance_id,
            aggregate_type=aggregate_type,
        )

    async def save_checkpoint(self, aggregate_type: str) -> dict[str, Any]:
        """Save a projection checkpoint for this agent instance."""
        return self.kernel.save_projection_snapshot(
            aggregate_type=aggregate_type,
            agent_id=self.instance_id,
        )

    # --- execution context (ADR-0007 Step 5) -----------------------------

    def execution_context(self):
        """Construct an ExecutionContext from this instance's identity.

        Allows callers that still hold an AgentInstance reference to get
        a minimal context for handler invocation. The Scheduler constructs
        ExecutionContext directly from WorkItem fields instead, so this
        method is primarily for backward compatibility and testing.
        """
        from .execution_context import ExecutionContext
        return ExecutionContext(
            instance_id=self.instance_id,
            actor=self.actor_id(),
            correlation_id=self.correlation_id or "",
            _kernel=self.kernel,
        )

    # --- event handling --------------------------------------------------

    async def dispatch(self, event: "Event") -> None:
        """Create a WorkItem and enqueue it in the Scheduler.

        The Scheduler handles execution lifecycle: timeout, retry, status
        transitions.  The Handler is pure business logic — it has no
        knowledge of the execution model.

        This is the Inversion of Control: the Runtime (Scheduler) decides
        WHEN and HOW the handler runs.  The handler just declares WHAT to
        do via @subscribe.
        """
        from .agent_scheduler import get_scheduler
        from .handler_registry import get_handler

        handler = get_handler(event.type)
        if handler is None:
            return

        from datetime import UTC, datetime
        self.last_active_at = datetime.now(UTC).isoformat()

        scheduler = get_scheduler(self.kernel)
        scheduler.enqueue(self.instance_id, self.actor_id(), event)

"""AgentDefinition — immutable declaration of an Agent type.

AgentDefinition is the static blueprint from which AgentInstances are spawned.
It is analogous to a class definition in OOP: one definition, many instances.

PRINCIPLE (MVP):
    Only include fields that have been validated by actual usage.
    Everything else is deferred.  Resist the urge to build a CRD.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubscriptionRule:
    """Declares which events an Agent subscribes to on the Event Log.

    All fields are optional filters; an omitted filter matches everything.

    This is NOT a separate bus abstraction. The Event Log IS the bus.
    A SubscriptionRule merely describes which rows the Agent's event loop
    should select (filtered by type and actor).

    The "AgentBus" (agent_bus.py) is not a new infrastructure layer — it is
    a SubscriptionManager that handles in-process dispatch on top of the
    already-existing Kernel Event Log.
    """

    event_type: str | None = None
    aggregate_type: str | None = None
    source_agent: str | None = None
    correlation_match: str | None = None


@dataclass(frozen=True)
class AgentDefinition:
    """Minimal immutable declaration of an Agent type.

    Fields kept in MVP are those proven necessary by Planner + Worker.
    All other metadata is deferred until a concrete use-case demands it.

    Projector First — there is NO reducer field. State is materialised
    through projectors (projectors_registry.py), not in-memory reducers.

    Event routing is handled by HandlerRegistry (handler_registry.py),
    not by the Agent itself.  Handlers are registered globally via
    @subscribe("EventType") and the Runtime dispatches automatically.
    """

    agent_id: str
    subscriptions: list[SubscriptionRule] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    version: str = "1.0.0"
    max_instances: int = 1
    stale_timeout_seconds: int = 3600

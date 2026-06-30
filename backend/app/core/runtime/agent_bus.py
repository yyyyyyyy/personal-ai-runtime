"""AgentBus — Subscription Manager for in-process Agent dispatch.

IMPORTANT architectural clarification:

    The Event Log IS the bus.  The Kernel's global, append-only event_log
    is already a fully capable pub/sub transport — every Agent can select
    its own event stream via the subscription rules.

    AgentBus is NOT a new infrastructure layer.  It is a SubscriptionManager:
    a lightweight routing table + async dispatch loop that delivers Kernel
    events to in-process AgentInstances without requiring each Agent to poll
    the event_log directly.

    Think of it as the "in-process fan-out" on top of the Event Log, not as
    a separate message broker.

Architecture:
    Agent A → emit_event → Global Event Log
                              ↙
    AgentBus (SubscriptionManager) → in-process dispatch → Agent B

This keeps the Global Event Log as the single source of truth while
allowing Agents to react to events without polling loops.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from .agent_definition import SubscriptionRule
from .event_bus import event_bus

if TYPE_CHECKING:
    from .kernel.event import Event

logger = logging.getLogger(__name__)

AgentHandler = Callable[["Event"], Awaitable[None]]


class AgentBus:
    """Lightweight inter-agent event bus.

    Agents subscribe with pattern-matching rules. When an event is published,
    the bus resolves matching subscribers and delivers the event to their
    per-agent queues.
    """

    def __init__(self):
        self._transport = event_bus
        self._running = False

        # agent_id → list of (SubscriptionRule, handler)
        self._subscriptions: dict[str, list[tuple[SubscriptionRule, AgentHandler]]] = {}

        # agent_id → asyncio.Queue for ordered event delivery
        self._queues: dict[str, asyncio.Queue] = {}

    # --- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Start the AgentBus."""
        if self._running:
            return
        self._running = True
        logger.info("AgentBus started")

    async def stop(self) -> None:
        """Stop the AgentBus."""
        self._running = False
        # Wake any waiting deliver_to callers
        for queue in self._queues.values():
            await queue.put(None)
        self._subscriptions.clear()
        self._queues.clear()
        logger.info("AgentBus stopped")

    # --- subscribe / unsubscribe -----------------------------------------

    def subscribe(
        self,
        agent_id: str,
        rule: SubscriptionRule,
        handler: AgentHandler,
    ) -> Callable[[], None]:
        """Register an agent's subscription.

        Returns an unsubscribe callable.
        """
        if agent_id not in self._subscriptions:
            self._subscriptions[agent_id] = []
        self._subscriptions[agent_id].append((rule, handler))
        logger.debug("AgentBus: %s subscribed to %s", agent_id, rule.event_type or "*")
        return lambda: self._unsubscribe(agent_id, rule, handler)

    def _unsubscribe(
        self,
        agent_id: str,
        rule: SubscriptionRule,
        handler: AgentHandler,
    ) -> None:
        subs = self._subscriptions.get(agent_id, [])
        self._subscriptions[agent_id] = [
            (r, h) for r, h in subs if not (r == rule and h is handler)
        ]

    def unsubscribe_all(self, agent_id: str) -> None:
        """Remove all subscriptions for an agent."""
        self._subscriptions.pop(agent_id, None)
        self._queues.pop(agent_id, None)

    def reset(self) -> None:
        """Remove ALL subscriptions from the bus — for test isolation."""
        self._subscriptions.clear()
        self._queues.clear()

    # --- publish / dispatch -----------------------------------------------

    async def publish(self, event: "Event") -> None:
        """Publish an event to the AgentBus.

        Invokes matching handler callbacks synchronously AND delivers to
        per-agent queues for agents that use the pull-based deliver_to API.
        Handler failures are logged but do not stop delivery to other subscribers.
        """
        subscriptions = self._resolve_subscriptions(event)
        for agent_id, handler in subscriptions:
            # 1. Deliver to per-agent queue (for deliver_to API)
            queue = self._get_queue(agent_id)
            await queue.put(event)
            # 2. Invoke handler directly
            try:
                await handler(event)
            except Exception as exc:
                logger.warning(
                    "AgentBus: handler for %s failed on %s: %s",
                    agent_id, event.type, exc,
                )

    def _resolve_subscriptions(
        self, event: "Event"
    ) -> list[tuple[str, AgentHandler]]:
        """Return (agent_id, handler) pairs for all matching subscriptions."""
        matched: list[tuple[str, AgentHandler]] = []
        for agent_id, subs in self._subscriptions.items():
            for rule, handler in subs:
                if self._rule_matches(rule, event):
                    matched.append((agent_id, handler))
        return matched

    def _rule_matches(self, rule: SubscriptionRule, event: "Event") -> bool:
        """Check whether a subscription rule matches an event."""
        if rule.event_type is not None:
            if not fnmatch.fnmatch(event.type, rule.event_type):
                return False
        if rule.aggregate_type is not None:
            if event.aggregate_type != rule.aggregate_type:
                return False
        if rule.source_agent is not None:
            if not event.actor.startswith(f"agent:{rule.source_agent}"):
                return False
        if rule.correlation_match is not None:
            cid = event.correlation_id or ""
            if not cid.startswith(rule.correlation_match):
                return False
        return True

    # --- delivery --------------------------------------------------------

    def _get_queue(self, agent_id: str) -> asyncio.Queue:
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue(maxsize=256)
        return self._queues[agent_id]

    async def deliver_to(self, agent_id: str, timeout: float = 5.0) -> "Event | None":
        """Block until an event is available for the agent, or timeout.

        This is the primary API for AgentInstance handlers to consume events
        from the bus.
        """
        queue = self._get_queue(agent_id)
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


# Global singleton for inter-agent communication.
agent_bus = AgentBus()
# registered in RuntimeContainer.inventory()

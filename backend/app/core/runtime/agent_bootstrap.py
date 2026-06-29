"""Runtime agent bootstrap — ensures a persistent agent for event routing (ADR Unification).

The Scheduler's execution chain requires an AgentInstance subscribed to the
AgentBus to route events (via AgentInstance.dispatch → Scheduler.enqueue →
handler). This module ensures one exists, reused across all bypass endpoints.
"""

from __future__ import annotations

_spawned = False


async def ensure_agent(kernel) -> None:
    """Spawn a single persistent agent subscribed to all unified event types.

    Only one agent is spawned (singleton). Chat, Approve, Execute, and
    BackgroundTask events all route through the same agent instance because
    handler_registry dispatches by event type, not by agent.
    """
    global _spawned
    if _spawned:
        return

    from app.core.agents.mvp import CHAT_DEFINITION
    from app.core.runtime.agent_bus import agent_bus

    registry = kernel.agent_registry
    instance = await registry.spawn(CHAT_DEFINITION, correlation_id="unified_agent")

    for rule in CHAT_DEFINITION.subscriptions:
        async def _dispatch(event, aid=instance.instance_id):
            inst = registry.get(aid)
            if inst is not None:
                await inst.dispatch(event)
        agent_bus.subscribe(agent_id=instance.instance_id, rule=rule, handler=_dispatch)

    _spawned = True

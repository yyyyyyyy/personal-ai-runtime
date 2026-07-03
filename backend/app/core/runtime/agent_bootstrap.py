"""Runtime agent bootstrap — ensures a persistent agent for event routing (ADR Unification).

The Scheduler's execution chain requires an AgentInstance to route events
(via AgentInstance.dispatch → Scheduler.enqueue → handler). This module
ensures one exists, reused across all handler endpoints.

v0.3: agent_bus removed — the persistent agent registers its dispatch
directly with the kernel via register_async_dispatcher.
"""

from __future__ import annotations

_spawned = False
_SINGLETON_INSTANCE_ID: str | None = None


async def ensure_agent(kernel) -> None:
    """Spawn a single persistent agent and register with kernel.

    Only one agent is spawned (singleton). Chat, Approve, Execute, and
    BackgroundTask events all route through the same agent instance because
    handler_registry dispatches by event type, not by agent.
    """
    global _spawned, _SINGLETON_INSTANCE_ID
    if _spawned:
        return

    from app.core.agents.mvp import CHAT_DEFINITION

    registry = kernel.agent_registry
    instance = await registry.spawn(CHAT_DEFINITION, correlation_id="unified_agent")
    _SINGLETON_INSTANCE_ID = instance.instance_id

    async def _dispatch(event, aid=instance.instance_id):
        inst = registry.get(aid)
        if inst is not None:
            await inst.dispatch(event)

    kernel.register_async_dispatcher(_dispatch)

    _spawned = True


def get_singleton_instance_id() -> str | None:
    """Return the singleton agent's instance_id, or None if not yet spawned."""
    return _SINGLETON_INSTANCE_ID

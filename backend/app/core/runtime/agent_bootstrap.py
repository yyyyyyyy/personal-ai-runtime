"""Agent bootstrap — ensures the event-to-WorkItem dispatcher is running.

v0.4.0: Agent lifecycle (spawn/start/stop/checkpoint) removed.
Scheduler is the only execution engine — no Agent abstraction needed.
"""
from __future__ import annotations

import app.core.agents.mvp  # noqa: F401 — registers @subscribe handlers

_started = False


async def ensure_scheduler(kernel) -> None:
    """Ensure the Scheduler is running and the event dispatcher is registered.

    Registers a kernel-level dispatcher that routes all emitted events to the
    Scheduler's WorkItem engine. Handler matching is done by handler_registry.
    """
    global _started
    if _started:
        return

    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import get_handler

    sch = get_scheduler(kernel)
    await sch.start()

    _AGENT_ID = "agent:primary"

    async def _dispatch_to_scheduler(event):
        handler = get_handler(event.type)
        if handler is None:
            return
        sch.enqueue(_AGENT_ID, _AGENT_ID, event)

    kernel.set_async_dispatcher(_dispatch_to_scheduler)
    _started = True


def reset_agent_bootstrap() -> None:
    """Clear the ``_started`` flag so the next ``ensure_scheduler`` re-binds.

    Pairs with ``reset_scheduler`` in ``runtime_container.reset()``. Without
    this, the module-level ``_started`` boolean survives across tests: the
    fresh Kernel has no ``_async_dispatcher`` registered, but
    ``ensure_scheduler`` short-circuits and the Scheduler loop is never
    (re)started on the new event loop. This was the root cause of the
    intermittent 504s in ``test_approval_resolve`` (ARCHITECTURE_SURVIVAL_REVIEW
    High #6).
    """
    global _started
    _started = False

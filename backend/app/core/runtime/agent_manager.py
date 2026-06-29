"""AgentManager — Multi-Agent orchestration via AgentBus.

The single-track multi-agent model:
  - AgentDefinition → AgentInstance (not ephemeral dicts)
  - Event-driven communication via AgentBus
  - Per-agent state isolation through Kernel
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

# Ensure the @subscribe handlers for Planner and Worker are registered.
# These imports trigger the decorators in planner_agent.py / worker_agent.py
# which populate handler_registry._registry so the Scheduler can find them.
import app.core.agents.mvp.planner_agent  # noqa: F401
import app.core.agents.mvp.worker_agent  # noqa: F401
from app.core.agents.mvp import PLANNER_DEFINITION, WORKER_DEFINITION
from app.core.runtime.agent_bus import agent_bus

if TYPE_CHECKING:
    from app.core.runtime.kernel.kernel import Kernel

logger = logging.getLogger(__name__)

# Timeout for an agent to process an event before we consider it stalled.
_AGENT_EVENT_TIMEOUT = 30.0


class AgentManager:
    """Orchestrates multi-agent tasks via AgentBus + Scheduler.

    Usage:
        manager = AgentManager(kernel_instance)
        result = await manager.run(user_request="Analyze sales data")
    """

    def __init__(self, kernel: "Kernel"):
        self._kernel = kernel

    async def run(self, user_request: str) -> dict:
        """Run a complete Planner → Worker pipeline.

        The Scheduler handles WorkItem execution — AgentManager's job is
        to spawn agents, wire up subscriptions, emit the initial event,
        and wait for the pipeline to complete.
        """
        from app.core.runtime.agent_scheduler import get_scheduler

        correlation_id = f"multi_{uuid.uuid4().hex[:12]}"

        # 1. Start the Scheduler
        scheduler = get_scheduler(self._kernel)
        await scheduler.start()

        # 2. Create the task identity (deferred emission — TaskCreated will
        #    be emitted AFTER all subscriptions are wired so AgentBus can
        #    route it.  Emission before subscription causes the event to be
        #    silently dropped.)
        import uuid as _uuid
        tid = f"task_{_uuid.uuid4().hex}"
        task = {"task_id": tid, "status": "pending"}
        task_id = task["task_id"]

        # 3. Spawn Planner and Worker
        registry = self._kernel.agent_registry
        planner = await registry.spawn(PLANNER_DEFINITION, correlation_id=correlation_id)
        worker = await registry.spawn(WORKER_DEFINITION, correlation_id=correlation_id)

        # 4. Subscribe — dispatch creates WorkItems, Scheduler executes them
        for rule in PLANNER_DEFINITION.subscriptions:
            agent_bus.subscribe(
                agent_id=planner.instance_id,
                rule=rule,
                handler=self._make_handler(planner.instance_id),
            )
        for rule in WORKER_DEFINITION.subscriptions:
            agent_bus.subscribe(
                agent_id=worker.instance_id,
                rule=rule,
                handler=self._make_handler(worker.instance_id),
            )

        # 5. Kick off — emit TaskCreated via Kernel (AgentBus picks it up)
        self._kernel.emit_event(
            type="TaskCreated",
            aggregate_type="task",
            aggregate_id=tid,
            payload={
                "name": f"Multi-Agent: {user_request[:60]}",
                "description": user_request,
                "priority": 0,
            },
            actor="user",
            correlation_id=correlation_id,
        )

        try:
            # Wait for pipeline completion by polling event log
            planner_events_seen = 0
            worker_events_seen = 0
            deadline = asyncio.get_event_loop().time() + _AGENT_EVENT_TIMEOUT

            while deadline > asyncio.get_event_loop().time():
                events = self._kernel.read_events(correlation_id=correlation_id)
                planner_events_seen = len([
                    e for e in events
                    if e.type in {"TaskCreated", "TaskPlanned", "TaskCompleted"}
                    and e.actor.startswith("agent:")
                ])
                worker_events_seen = len([
                    e for e in events
                    if e.type in {"TaskPlanned", "TaskCompleted"}
                    and e.actor.startswith("agent:")
                ])
                if planner_events_seen >= 2 and worker_events_seen >= 1:
                    break
                await asyncio.sleep(0.2)

            # 6. Clean up
            agent_bus.unsubscribe_all(planner.instance_id)
            agent_bus.unsubscribe_all(worker.instance_id)
            await scheduler.stop()
            await registry.kill(planner.instance_id, reason="completed")
            await registry.kill(worker.instance_id, reason="completed")

            return {
                "status": "ok",
                "task_id": task_id,
                "correlation_id": correlation_id,
                "planner_events": planner_events_seen,
                "worker_events": worker_events_seen,
            }
        except Exception:
            scheduler._running = False
            await registry.kill(planner.instance_id, reason="error")
            await registry.kill(worker.instance_id, reason="error")
            raise

    def _make_handler(self, instance_id: str):
        """Route events to AgentInstance.dispatch() → Scheduler.enqueue().

        AgentInstance.dispatch creates a WorkItem and enqueues it.
        The Scheduler handles the execution lifecycle.
        """

        async def handler(event):
            registry = self._kernel.agent_registry
            instance = registry.get(instance_id)
            if instance is None:
                return
            await instance.dispatch(event)

        return handler

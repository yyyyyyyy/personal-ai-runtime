"""AgentRegistry — manages AgentInstance lifecycle.

Co-exists with the legacy _active_agents dictionary during the migration
period. Once migration completes, _active_agents will be removed and the
AgentRegistry becomes the single source of truth for agent instances.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .agent_definition import AgentDefinition
from .agent_instance import AgentInstance

if TYPE_CHECKING:
    from .kernel.kernel import Kernel

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages the lifecycle of AgentInstance objects.

    - Spawns new instances from AgentDefinitions.
    - Tracks running/paused/terminated instances.
    - Cleans up stale instances.
    - Enforces max_instances limits per AgentDefinition.
    """

    def __init__(self, kernel: "Kernel"):
        self._kernel = kernel
        self._instances: dict[str, AgentInstance] = {}

    # --- lookup ----------------------------------------------------------

    def get(self, instance_id: str) -> AgentInstance | None:
        """Return an instance by id, or None."""
        return self._instances.get(instance_id)

    def __len__(self) -> int:
        """Number of tracked instances (running+paused+terminated)."""
        return len(self._instances)

    def list_by_status(self, status: str) -> list[AgentInstance]:
        """Return all instances with the given status."""
        return [i for i in self._instances.values() if i.status == status]

    def list_by_definition(self, agent_id: str) -> list[AgentInstance]:
        """Return all instances of a given AgentDefinition type."""
        return [i for i in self._instances.values() if i.definition.agent_id == agent_id]

    def count_running(self, agent_id: str) -> int:
        """Count running instances for a given definition type."""
        return len([
            i for i in self._instances.values()
            if i.definition.agent_id == agent_id and i.status in ("running", "spawning")
        ])

    # --- lifecycle -------------------------------------------------------

    async def spawn(
        self,
        definition: AgentDefinition,
        correlation_id: str | None = None,
    ) -> AgentInstance:
        """Create and start a new AgentInstance from a definition.

        Raises RuntimeError if max_instances would be exceeded.
        """
        if self.count_running(definition.agent_id) >= definition.max_instances:
            raise RuntimeError(
                f"Max instances ({definition.max_instances}) reached for "
                f"'{definition.agent_id}'"
            )

        instance = AgentInstance(
            definition=definition,
            kernel=self._kernel,
            correlation_id=correlation_id,
        )
        self._instances[instance.instance_id] = instance
        await instance.start()

        # Emit GrantCreated events for each capability (event-sourced grants).
        # Skip when grant_events table doesn't exist (integration tests with Alembic).
        try:
            self._kernel.query_state("grant_events", limit=1)
            table_ok = True
        except Exception:
            table_ok = False

        if table_ok:
            for tool in definition.tools:
                self._kernel.emit_event(
                    "GrantCreated",
                    "grant",
                    f"grant_{instance.instance_id}_{tool}",
                    payload={
                        "principal_id": instance.instance_id,
                        "capability": tool,
                    },
                    actor="kernel",
                    correlation_id=correlation_id,
                )

        logger.info(
            "Spawned agent '%s' (instance=%s)", definition.agent_id, instance.instance_id
        )
        return instance

    async def kill(self, instance_id: str, reason: str = "completed") -> None:
        """Terminate an agent instance."""
        instance = self._instances.get(instance_id)
        if instance is None:
            logger.warning("Attempted to kill unknown instance: %s", instance_id)
            return
        await instance.stop(reason)
        del self._instances[instance_id]
        logger.info(
            "Killed agent instance %s: %s", instance_id, reason
        )

    async def cleanup_stale(self, max_age_seconds: int | None = None) -> list[str]:
        """Remove instances that have been idle beyond their stale timeout.

        Returns the list of evicted instance_ids.
        """
        now = time.time()
        stale_ids: list[str] = []
        for instance in list(self._instances.values()):
            timeout = max_age_seconds or instance.definition.stale_timeout_seconds
            last_active = instance.last_active_at
            if last_active is None:
                continue
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(last_active).timestamp()
                if now - ts > timeout:
                    stale_ids.append(instance.instance_id)
            except (ValueError, OSError):
                pass

        for sid in stale_ids:
            await self.kill(sid, reason="stale_timeout")
        return stale_ids

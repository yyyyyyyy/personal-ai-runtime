"""IdentityResolver — adapt actor strings to typed Principals (ADR-0007 Step 8).

Bridges the legacy actor-string world to typed Principals. Once all call
sites pass Principals directly, this adapter can be removed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .principal import Principal

if TYPE_CHECKING:
    from .kernel.kernel import Kernel


class IdentityResolver:
    """Resolve actor strings to Principals."""

    def resolve(self, actor: str, kernel: "Kernel") -> Principal:
        if actor.startswith("agent:"):
            instance_id = actor.split(":", 1)[1]
            instance = kernel.agent_registry.get(instance_id)
            tools = list(instance.definition.tools) if instance else []
            return Principal.agent(instance_id, tools)
        if actor in ("system", "kernel"):
            return Principal.system()
        return Principal.user(actor)


identity_resolver = IdentityResolver()

"""IdentityResolver — adapt actor strings to typed Principals (ADR-0007 Step 8).

Bridges the legacy actor-string world to typed Principals.
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
            # Single-agent runtime: all agent identities get wildcard capabilities
            instance_id = actor.split(":", 1)[1]
            return Principal.agent(instance_id, ["*"])
        if actor in ("system", "kernel"):
            return Principal.system()
        return Principal.user(actor)


identity_resolver = IdentityResolver()

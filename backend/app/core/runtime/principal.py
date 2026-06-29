"""Principal — typed runtime identity (ADR-0007 Step 8).

Replaces raw actor strings in capability authorization. A Principal carries
principal_id, type, actor (backward-compat), and allowed_capabilities.

Frozen so it can be safely passed across execution boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Typed runtime identity — replaces raw actor strings in authorization."""

    principal_id: str
    type: str
    actor: str
    allowed_capabilities: tuple[str, ...]

    @classmethod
    def system(cls) -> "Principal":
        return cls("system", "system", "system", ("*",))

    @classmethod
    def user(cls, user_id: str = "user") -> "Principal":
        return cls(user_id, "user", user_id, ("*",))

    @classmethod
    def agent(cls, instance_id: str, tools: list[str]) -> "Principal":
        return cls(instance_id, "agent", f"agent:{instance_id}", tuple(tools))

    def is_capable_of(self, capability: str) -> bool:
        """Check if this principal is authorized for a capability."""
        return "*" in self.allowed_capabilities or capability in self.allowed_capabilities

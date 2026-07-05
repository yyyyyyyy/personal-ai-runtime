"""Execution identity — typed Principal, resolver, and scoping (ADR-0007 Step 8).

Merged from principal.py + identity_resolver.py + execution_scope.py (v0.7.0).
These three concepts are the same concern: "who is executing and what are they allowed to do."
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .kernel.kernel import Kernel


# ── Principal (typed runtime identity) ────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """Typed runtime identity — replaces raw actor strings in authorization.

    Only two principal types are recognized in the single-user runtime:
    ``system`` (kernel/runtime loops) and ``user`` (interactive user).
    The former ``agent`` principal type was removed in v0.9.0 — it had no
    production emitter and its Gate 2 grant check was fail-closed dead.
    """

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

    def is_capable_of(self, capability: str) -> bool:
        return "*" in self.allowed_capabilities or capability in self.allowed_capabilities


# ── Identity Resolver ─────────────────────────────────────────────────────────

class IdentityResolver:
    """Resolve actor strings to Principals.

    Actor strings starting with ``agent:`` (legacy) and the named runtime
    actors ``scheduler`` / ``executor`` / ``background`` / ``kernel`` all
    resolve to the ``system`` principal — they run inside the trusted
    Runtime and are not subject to per-user approval gating.
    """

    _RUNTIME_ACTORS = frozenset({"system", "kernel", "scheduler", "executor", "background"})

    def resolve(self, actor: str, kernel: "Kernel") -> Principal:
        if actor.startswith("agent:") or actor in self._RUNTIME_ACTORS:
            return Principal.system()
        return Principal.user(actor)


identity_resolver = IdentityResolver()


# ── Execution Scope (ContextVar binding) ─────────────────────────────────────

_current_execution_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_execution_id", default=None,
)

RUNTIME_OWNERSHIP_ACTORS = frozenset({"scheduler", "executor", "background"})


def get_current_execution_id() -> str | None:
    return _current_execution_id.get()


def actor_requires_execution_ownership(actor: str) -> bool:
    if actor.startswith("agent:"):
        return True
    return actor in RUNTIME_OWNERSHIP_ACTORS


@contextmanager
def execution_scope(execution_id: str) -> Iterator[None]:
    token = _current_execution_id.set(execution_id)
    try:
        yield
    finally:
        _current_execution_id.reset(token)

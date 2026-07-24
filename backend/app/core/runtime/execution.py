"""Execution identity — typed Principal, resolver, and scoping (Execution 契约 §8).

Principal, identity resolution, and execution scoping are one concern:
"who is executing and what are they allowed to do."
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from .kernel.event import Event
    from .kernel.kernel import Kernel


# ── Principal (typed runtime identity) ────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """Typed runtime identity — replaces raw actor strings in authorization.

    Only two principal types are recognized in the single-user runtime:
    ``system`` (kernel/runtime loops) and ``user`` (interactive user).
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

    Actor strings starting with ``agent:`` / ``runtime:`` and the named
    actors ``scheduler`` / ``executor`` / ``background`` / ``kernel`` all
    resolve to the ``system`` principal — they run inside the trusted
    Runtime and are not subject to per-user approval gating.
    """

    _RUNTIME_ACTORS = frozenset({"system", "kernel", "scheduler", "executor", "background"})

    def resolve(self, actor: str, kernel: "Kernel") -> Principal:
        if (
            actor.startswith("agent:")
            or actor.startswith("runtime:")
            or actor in self._RUNTIME_ACTORS
        ):
            return Principal.system()
        return Principal.user(actor)


identity_resolver = IdentityResolver()


def reset_identity_resolver() -> None:
    """No-op — IdentityResolver is stateless (frozenset + string ops)."""
    pass


# ── Execution Scope (ContextVar binding) ─────────────────────────────────────

_current_execution_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_execution_id", default=None,
)

RUNTIME_OWNERSHIP_ACTORS = frozenset({"scheduler", "executor", "background"})


def get_current_execution_id() -> str | None:
    return _current_execution_id.get()


def actor_requires_execution_ownership(actor: str) -> bool:
    if actor.startswith("agent:") or actor.startswith("runtime:"):
        return True
    return actor in RUNTIME_OWNERSHIP_ACTORS


@contextmanager
def execution_scope(execution_id: str) -> Iterator[None]:
    token = _current_execution_id.set(execution_id)
    try:
        yield
    finally:
        _current_execution_id.reset(token)


# ── Cooperative cancellation ───────────────────────────────────────────────
#
# Cancelled Lane A runs terminate via ExecutionFailed(error="cancelled").
# Cancelled background work items terminate via WorkItemStatusChanged(status=
# "cancelled") from the cancel API; handlers observe ``exec_{work_item_id}``.
#
# Process-local flags accelerate cooperative checks mid-flight. Durable
# authority is the projection: Scheduler.request_cancel emits ExecutionFailed
# for pending **and** in-flight items before task.cancel() (ADR-R010), so
# restart recovery (running→pending) cannot resurrect a cancelled execution.

_cancelled_executions: set[str] = set()


def request_cancel_execution(execution_id: str) -> None:
    if execution_id:
        _cancelled_executions.add(execution_id)


def is_execution_cancelled(execution_id: str) -> bool:
    return bool(execution_id) and execution_id in _cancelled_executions


def clear_execution_cancel(execution_id: str) -> None:
    _cancelled_executions.discard(execution_id)


def clear_all_cancels() -> None:
    """Test helper."""
    _cancelled_executions.clear()


# ── ExecutionContext (folded from execution_context.py) ──────────────────

@dataclass
class ExecutionContext:
    """Minimal runtime context passed to handlers.

    Carries only what a handler needs to execute: identity (for event
    emission and logging), the kernel reference (for emit), and the
    Principal (typed identity for capability authorization).
    """

    instance_id: str
    actor: str
    correlation_id: str
    _kernel: "Kernel"
    principal: Principal = field(default_factory=Principal.system)

    # Execution Ownership: the Execution aggregate_id that owns
    # this handler run. Every capability invocation inside this handler
    # MUST be attributable to this Execution.
    execution_id: str = ""

    def emit(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
        caused_by: str | None = None,
    ) -> "Event":
        """Emit an event through the Kernel with this context's actor."""
        return self._kernel.emit_event(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            actor=self.actor,
            caused_by=caused_by,
            correlation_id=self.correlation_id or None,
        )

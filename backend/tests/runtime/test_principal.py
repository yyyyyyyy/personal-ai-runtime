"""ADR-0007 Step 8 — Principal and IdentityResolver tests.

v0.9.0: agent principal tests removed — Principal.agent was deleted.
Agent actor strings now resolve to system principal (they only appear
internally in the Scheduler, which is fully trusted Runtime code).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "principal.db")))


# ── Principal basics ───────────────────────────────────────────────────


def test_principal_system_factory():
    from app.core.runtime.execution import Principal

    p = Principal.system()
    assert p.principal_id == "system"
    assert p.type == "system"
    assert p.actor == "system"
    assert "*" in p.allowed_capabilities


def test_principal_user_factory():
    from app.core.runtime.execution import Principal

    p = Principal.user("alice")
    assert p.principal_id == "alice"
    assert p.type == "user"
    assert p.actor == "alice"


def test_principal_is_frozen():
    from app.core.runtime.execution import Principal

    p = Principal.system()
    with pytest.raises(Exception):
        p.principal_id = "hacker"  # type: ignore[misc]


def test_principal_user_is_capable_of_anything():
    from app.core.runtime.execution import Principal

    user = Principal.user()
    assert user.is_capable_of("anything")


# ── IdentityResolver ───────────────────────────────────────────────────


def test_resolver_agent_actor_maps_to_system(kernel):
    """Agent actors resolve to system principal in single-user runtime.

    Scheduler emits ``agent:primary`` internally; since v0.9.0 there is no
    separate agent principal type. The Scheduler is trusted Runtime code
    and runs as system identity.
    """
    from app.core.runtime.execution import Principal, identity_resolver

    p = identity_resolver.resolve("agent:primary", kernel)
    assert isinstance(p, Principal)
    assert p.type == "system"
    assert p.principal_id == "system"
    assert "*" in p.allowed_capabilities


def test_resolver_system_actor(kernel):
    from app.core.runtime.execution import identity_resolver

    p = identity_resolver.resolve("system", kernel)
    assert p.type == "system"
    assert p.principal_id == "system"

    p2 = identity_resolver.resolve("kernel", kernel)
    assert p2.type == "system"


def test_resolver_runtime_actors_map_to_system(kernel):
    """scheduler / executor / background / kernel are trusted Runtime actors."""
    from app.core.runtime.execution import identity_resolver

    for actor in ("scheduler", "executor", "background", "kernel"):
        p = identity_resolver.resolve(actor, kernel)
        assert p.type == "system", f"{actor!r} should map to system, got {p.type}"


def test_resolver_user_actor(kernel):
    from app.core.runtime.execution import identity_resolver

    p = identity_resolver.resolve("user", kernel)
    assert p.type == "user"
    assert p.principal_id == "user"

    # Any non-runtime, non-system actor is treated as a user.
    p2 = identity_resolver.resolve("alice", kernel)
    assert p2.type == "user"
    assert p2.principal_id == "alice"


# ── ExecutionContext integration ───────────────────────────────────────


def test_execution_context_has_principal(kernel):
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.execution import Principal

    p = Principal.user("test_user")
    ctx = ExecutionContext(
        instance_id="aginst_test",
        actor="agent:aginst_test",
        correlation_id="corr",
        _kernel=kernel,
        principal=p,
    )
    assert ctx.principal is p
    assert ctx.principal.type == "user"


def test_execution_context_default_principal(kernel):
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.execution import Principal

    ctx = ExecutionContext(
        instance_id="aginst_test",
        actor="agent:aginst_test",
        correlation_id="corr",
        _kernel=kernel,
    )
    assert isinstance(ctx.principal, Principal)
    # agent: actors now resolve to system (v0.9.0).
    assert ctx.principal.type == "system"

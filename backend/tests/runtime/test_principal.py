"""ADR-0007 Step 8 — Principal and IdentityResolver tests."""

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
    from app.core.runtime.principal import Principal

    p = Principal.system()
    assert p.principal_id == "system"
    assert p.type == "system"
    assert p.actor == "system"
    assert "*" in p.allowed_capabilities


def test_principal_user_factory():
    from app.core.runtime.principal import Principal

    p = Principal.user("alice")
    assert p.principal_id == "alice"
    assert p.type == "user"
    assert p.actor == "alice"


def test_principal_agent_factory():
    from app.core.runtime.principal import Principal

    p = Principal.agent("aginst_abc", ["web_search", "read_file"])
    assert p.principal_id == "aginst_abc"
    assert p.type == "agent"
    assert p.actor == "agent:aginst_abc"
    assert p.allowed_capabilities == ("web_search", "read_file")


def test_principal_is_frozen():
    from app.core.runtime.principal import Principal

    p = Principal.system()
    with pytest.raises(Exception):
        p.principal_id = "hacker"  # type: ignore[misc]


def test_principal_is_capable_of():
    from app.core.runtime.principal import Principal

    wildcard = Principal.agent("a", ["*"])
    limited = Principal.agent("b", ["web_search"])
    user = Principal.user()

    assert wildcard.is_capable_of("anything")
    assert limited.is_capable_of("web_search")
    assert not limited.is_capable_of("shell_exec")
    assert user.is_capable_of("anything")


# ── IdentityResolver ───────────────────────────────────────────────────


def test_resolver_agent_actor(kernel):
    import asyncio

    from app.core.runtime.agent_definition import AgentDefinition
    from app.core.runtime.identity_resolver import identity_resolver
    from app.core.runtime.principal import Principal

    async def _run():
        registry = kernel.agent_registry
        definition = AgentDefinition(
            agent_id="test_agent",
            tools=["web_search", "read_file"],
        )
        instance = await registry.spawn(definition)
        p = identity_resolver.resolve(f"agent:{instance.instance_id}", kernel)
        assert isinstance(p, Principal)
        assert p.type == "agent"
        assert p.principal_id == instance.instance_id
        assert "web_search" in p.allowed_capabilities
        await registry.kill(instance.instance_id)

    asyncio.run(_run())


def test_resolver_system_actor(kernel):
    from app.core.runtime.identity_resolver import identity_resolver

    p = identity_resolver.resolve("system", kernel)
    assert p.type == "system"
    assert p.principal_id == "system"

    p2 = identity_resolver.resolve("kernel", kernel)
    assert p2.type == "system"


def test_resolver_user_actor(kernel):
    from app.core.runtime.identity_resolver import identity_resolver

    p = identity_resolver.resolve("user", kernel)
    assert p.type == "user"
    assert p.principal_id == "user"

    p2 = identity_resolver.resolve("background", kernel)
    assert p2.type == "user"
    assert p2.principal_id == "background"


def test_resolver_unregistered_agent(kernel):
    from app.core.runtime.identity_resolver import identity_resolver

    p = identity_resolver.resolve("agent:nonexistent_instance", kernel)
    assert p.type == "agent"
    assert p.allowed_capabilities == ()


# ── ExecutionContext integration ───────────────────────────────────────


def test_execution_context_has_principal(kernel):
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.principal import Principal

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
    from app.core.runtime.principal import Principal

    ctx = ExecutionContext(
        instance_id="aginst_test",
        actor="agent:aginst_test",
        correlation_id="corr",
        _kernel=kernel,
    )
    assert isinstance(ctx.principal, Principal)
    assert ctx.principal.type == "system"

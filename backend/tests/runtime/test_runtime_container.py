"""Tests for RuntimeContainer — centralised DI lifecycle and test isolation."""


def test_runtime_container_lazy_load():
    """All properties resolve lazily without circular imports."""
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    assert c._kernel is None
    assert c._agent_bus is None
    assert c._capability_policy is None
    assert c._taint_registry is None


def test_runtime_container_kernel_access():
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    k = c.kernel
    assert k is not None
    assert c.kernel is k


def test_runtime_container_agent_bus_access():
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    ab = c.agent_bus
    assert ab is not None
    assert c.agent_bus is ab


def test_runtime_container_reset_clears_agent_bus():
    from app.core.runtime.agent_bus import SubscriptionRule, agent_bus
    from app.core.runtime.runtime_container import runtime

    agent_bus.subscribe("test-agent", SubscriptionRule(event_type="TestEvent"), lambda e: None)
    assert "test-agent" in agent_bus._subscriptions

    runtime.reset()
    assert "test-agent" not in agent_bus._subscriptions


def test_runtime_container_reset_clears_taint():
    from app.core.runtime.runtime_container import runtime
    from app.core.runtime.taint import taint_registry

    taint_registry.mark("corr-test", source="external_ingestion", reason="test")
    assert taint_registry.is_tainted("corr-test")

    runtime.reset()
    assert not taint_registry.is_tainted("corr-test")


def test_runtime_container_reset_clears_capability_policy():
    from app.core.runtime.capability_policy import capability_policy
    from app.core.runtime.runtime_container import runtime

    capability_policy.register_external_tool("test-ext-write", risk="high")
    assert capability_policy.risk_for("test-ext-write") == "high"

    runtime.reset()
    assert capability_policy.risk_for("test-ext-write") == "low"


def test_runtime_container_reset_clears_source_registry():
    from app.core.runtime.governance.context_pipeline import _store_sources, get_sources
    from app.core.runtime.runtime_container import runtime

    _store_sources("test-conv", [{"type": "memory", "id": "m1"}])
    sources = get_sources("test-conv")
    assert len(sources) == 1

    runtime.reset()
    sources = get_sources("test-conv")
    assert sources == []


def test_global_runtime_singleton_is_available():
    from app.core.runtime.runtime_container import runtime

    assert runtime is not None
    k = runtime.kernel
    assert k is not None

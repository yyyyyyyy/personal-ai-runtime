"""Tests for RuntimeContainer — centralised DI lifecycle and test isolation."""


def test_runtime_container_lazy_load():
    """All properties resolve lazily without circular imports."""
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    assert c._kernel is None
    assert len(c._inventory) == 0


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
    # v0.4.0: CapabilityGovernance replaced CapabilityPolicy
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.runtime_container import runtime

    capability_governance.register_external_tool("test-ext-write", risk="high")
    assert capability_governance.risk_for("test-ext-write") == "high"

    runtime.reset()
    assert capability_governance.risk_for("test-ext-write") == "low"


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


def test_runtime_container_inventory():
    """inventory() returns registered subsystems after lazy resolution."""
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    # Before any access, inventory is empty (lazy init)
    inv = c.inventory()
    assert isinstance(inv, list)

    # Touch a few subsystems to populate the registry
    c.agent_bus
    c.capability_governance
    c.taint_registry
    c.kernel

    inv = c.inventory()
    names = {e["name"] for e in inv}
    assert "kernel" in names
    assert "agent_bus" in names
    assert "capability_governance" in names
    assert "taint_registry" in names
    # Each entry has the expected keys
    for entry in inv:
        assert "name" in entry
        assert "module" in entry
        assert "class" in entry
        assert entry["class"] != ""

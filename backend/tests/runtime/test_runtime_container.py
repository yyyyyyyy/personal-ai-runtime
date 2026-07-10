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


def test_runtime_container_new_properties():
    """v0.5.0: All module-level singletons now accessible via RuntimeContainer."""
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()

    # All properties should resolve without error
    assert c.kernel is not None
    assert c.capability_governance is not None
    assert c.taint_registry is not None
    assert c.context_pipeline is not None
    assert c.fragment_registry is not None
    assert c.mcp_hub is not None
    assert c.llm_router is not None
    assert c.memory_engine is not None
    assert c.memory_extractor is not None
    assert c.state_manager is not None
    assert c.runtime_config is not None
    assert c.db is not None
    assert c.vector_store is not None
    assert c.runtime_loop is not None
    assert c.world_model is not None
    assert c.prompt_compiler is not None
    assert c.telemetry is not None

    inv = c.inventory()
    names = {e["name"] for e in inv}
    expected = {
        "kernel", "capability_governance", "taint_registry",
        "context_pipeline", "fragment_registry", "mcp_hub", "llm_router",
        "memory_engine", "memory_extractor", "state_manager", "runtime_config",
        "db", "vector_store", "runtime_loop", "world_model", "prompt_compiler",
        "telemetry",
    }
    assert expected <= names, f"Missing: {expected - names}"


def test_runtime_container_inventory():
    """inventory() returns registered subsystems after lazy resolution."""
    from app.core.runtime.runtime_container import RuntimeContainer

    c = RuntimeContainer()
    # Before any access, inventory is empty (lazy init)
    inv = c.inventory()
    assert isinstance(inv, list)

    # Touch a few subsystems to populate the registry
    c.capability_governance
    c.taint_registry
    c.kernel
    c.llm_router
    c.mcp_hub
    c.memory_engine

    inv = c.inventory()
    names = {e["name"] for e in inv}
    assert "kernel" in names
    assert "capability_governance" in names
    assert "taint_registry" in names
    assert "llm_router" in names
    assert "mcp_hub" in names
    assert "memory_engine" in names
    # Each entry has the expected keys
    for entry in inv:
        assert "name" in entry
        assert "module" in entry
        assert "class" in entry
        assert entry["class"] != ""


def test_reset_clears_module_singletons_handlers():
    """reset() must clear handler_registry so tests do not leak handlers."""
    from app.core.runtime.handler_registry import get_handler, subscribe

    @subscribe("TestLeakedEvent")
    async def _handler(ctx, event):
        pass

    assert get_handler("TestLeakedEvent") is _handler

    from app.core.runtime.runtime_container import runtime
    runtime.reset()

    assert get_handler("TestLeakedEvent") is None


def test_reset_clears_module_singletons_reactions():
    """reset() must clear reaction_registry so tests do not leak reactions."""
    from app.core.runtime.reaction_registry import (
        Reaction,
        ReactionWhen,
        get_reaction_registry,
    )

    registry = get_reaction_registry()
    registry.register(Reaction("test_leaked", when=ReactionWhen(event_type="Foo")))
    assert any(r.name == "test_leaked" for r in registry._reactions.values())

    from app.core.runtime.runtime_container import runtime
    runtime.reset()

    assert all(r.name != "test_leaked" for r in registry._reactions.values())


def test_reset_clears_module_singletons_fragments():
    """reset() must clear fragment_registry so tests do not leak fragments."""
    from app.context_runtime import ContextFragment, fragment_registry

    frag = ContextFragment(id="test.leaked", priority=10)
    fragment_registry.register(frag)
    assert fragment_registry.get("test.leaked") is frag

    from app.core.runtime.runtime_container import runtime
    runtime.reset()

    assert fragment_registry.get("test.leaked") is None


def test_reset_clears_module_singletons_scheduler():
    """reset() must reset scheduler singleton so tests do not leak scheduler state."""
    from app.core.runtime.agent_scheduler import get_scheduler

    # Force creation of scheduler singleton by querying it once.
    from app.core.runtime.kernel_instance import kernel
    get_scheduler(kernel)

    from app.core.runtime import agent_scheduler
    assert agent_scheduler._scheduler is not None

    from app.core.runtime.runtime_container import runtime
    runtime.reset()

    assert agent_scheduler._scheduler is None

"""Runtime Container — centralized registry for Runtime subsystems.

Every subsystem singleton is accessible from a single container.
This enables single-point reset() for test isolation and future
multi-Kernel instances.

v0.5.0: All module-level singletons are now lazy proxies that forward to
the matching RuntimeContainer property. The container is the sole owner of
each instance; ``reset()`` rebuilds them from scratch. Old ``from x import
singleton`` import paths keep working because the proxy transparently
delegates attribute access.

Architecture target: global singletons 15+ → 0 (all registered).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.context_runtime import FragmentRegistry
    from app.core.agents.llm_failover import LLMRouter
    from app.core.agents.memory_engine import MemoryEngine
    from app.core.agents.memory_extractor import MemoryExtractor
    from app.core.harness.mcp_hub import MCPHub
    from app.core.runtime.capability_governance import CapabilityGovernance
    from app.core.runtime.governance.context_pipeline import ContextPipeline
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.runtime_config import RuntimeConfig
    from app.core.runtime.state_manager import StateManager
    from app.core.runtime.taint import TaintRegistry
    from app.core.runtime.task_engine import TaskEngine
    from app.core.runtime.trigger_engine import TriggerEngine


class _LazyProxy:
    """Transparent forwarder to a RuntimeContainer property.

    Module-level singletons are replaced by ``_LazyProxy(lambda: runtime.x)``
    so that legacy ``from module import singleton`` imports keep working
    while the container remains the single source of truth. Every attribute
    *read* is delegated to the underlying instance; writes/deletes stay on
    the proxy itself so ``unittest.mock.patch`` can swap a method without
    touching the shared underlying instance.

    The ``__new__`` overload below tells mypy that constructing a proxy
    yields ``Any``, so call sites like ``kernel = _LazyProxy(...)`` type-
    check     against the real Kernel API rather than against _LazyProxy itself.
    """

    def __init__(self, factory: "Any"):
        self.__dict__["_factory"] = factory

    # NOTE: no __slots__ — the proxy keeps its own __dict__ for attributes
    # installed by callers (notably unittest.mock.patch) so they do not leak
    # into the shared underlying instance.

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails (i.e. the name is
        # not in self.__dict__), so we forward to the underlying instance.
        return getattr(self._factory(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Persist on the proxy itself; do not mutate the shared instance.
        self.__dict__[name] = value

    def __delattr__(self, name: str) -> None:
        if name in self.__dict__:
            del self.__dict__[name]
        else:
            delattr(self._factory(), name)

    def __bool__(self) -> bool:
        return bool(self._factory())

    def __repr__(self) -> str:
        try:
            return repr(self._factory())
        except Exception as exc:
            return f"<_LazyProxy factory-error: {exc}>"


class RuntimeContainer:
    """Holds all Runtime subsystem references for centralized lifecycle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._inventory: list[dict] = []
        # kernel
        self._kernel: "Kernel | None" = None
        # governance
        self._capability_governance: "CapabilityGovernance | None" = None
        self._taint_registry: "TaintRegistry | None" = None
        # context
        self._context_pipeline: "ContextPipeline | None" = None
        self._fragment_registry: "FragmentRegistry | None" = None
        # tools
        self._mcp_hub: "MCPHub | None" = None
        # agents / memory
        self._llm_router: "LLMRouter | None" = None
        self._memory_engine: "MemoryEngine | None" = None
        self._memory_extractor: "MemoryExtractor | None" = None
        # runtime state
        self._state_manager: "StateManager | None" = None
        self._runtime_config: "RuntimeConfig | None" = None

    def inventory(self) -> list[dict]:
        """Return list of registered subsystems (lazily populated on first access)."""
        return list(self._inventory)

    def _register(self, name: str, module: str, cls_name: str) -> None:
        """Register a subsystem in the inventory if not already present."""
        if not any(e["name"] == name for e in self._inventory):
            self._inventory.append({"name": name, "module": module, "class": cls_name})

    # ── Kernel ────────────────────────────────────────────────────────

    @property
    def kernel(self) -> "Kernel":
        if self._kernel is None:
            from app.core.runtime.kernel.kernel import Kernel
            self._kernel = Kernel()
            self._register("kernel", "app.core.runtime.kernel.kernel", "Kernel")
        return self._kernel

    @kernel.setter
    def kernel(self, value: "Kernel") -> None:
        self._kernel = value

    # ── Governance ─────────────────────────────────────────────────────

    @property
    def capability_governance(self) -> "CapabilityGovernance":
        if self._capability_governance is None:
            from app.core.runtime.capability_governance import CapabilityGovernance
            self._capability_governance = CapabilityGovernance()
            self._register(
                "capability_governance",
                "app.core.runtime.capability_governance",
                "CapabilityGovernance",
            )
        return self._capability_governance

    @property
    def taint_registry(self) -> "TaintRegistry":
        if self._taint_registry is None:
            from app.core.runtime.taint import TaintRegistry
            self._taint_registry = TaintRegistry()
            self._register("taint_registry", "app.core.runtime.taint", "TaintRegistry")
        return self._taint_registry

    # ── Context ────────────────────────────────────────────────────────

    @property
    def context_pipeline(self) -> "ContextPipeline":
        if self._context_pipeline is None:
            from app.core.runtime.governance.context_pipeline import ContextPipeline
            self._context_pipeline = ContextPipeline()
            self._register(
                "context_pipeline",
                "app.core.runtime.governance.context_pipeline",
                "ContextPipeline",
            )
        return self._context_pipeline

    @property
    def fragment_registry(self) -> "FragmentRegistry":
        if self._fragment_registry is None:
            from app.context_runtime import fragment_registry as fr
            self._fragment_registry = fr
            self._register("fragment_registry", "app.context_runtime", type(fr).__name__)
        return self._fragment_registry

    # ── Tools ──────────────────────────────────────────────────────────

    @property
    def mcp_hub(self) -> "MCPHub":
        if self._mcp_hub is None:
            from app.core.harness.mcp_hub import MCPHub
            self._mcp_hub = MCPHub()
            self._register("mcp_hub", "app.core.harness.mcp_hub", "MCPHub")
        return self._mcp_hub

    # ── Agents / Memory ────────────────────────────────────────────────

    @property
    def llm_router(self) -> "LLMRouter":
        if self._llm_router is None:
            from app.core.agents.llm_failover import LLMRouter
            self._llm_router = LLMRouter()
            self._register("llm_router", "app.core.agents.llm_failover", "LLMRouter")
        return self._llm_router

    @property
    def memory_engine(self) -> "MemoryEngine":
        if self._memory_engine is None:
            from app.core.agents.memory_engine import MemoryEngine
            self._memory_engine = MemoryEngine()
            self._register(
                "memory_engine", "app.core.agents.memory_engine", "MemoryEngine",
            )
        return self._memory_engine

    @property
    def memory_extractor(self) -> "MemoryExtractor":
        if self._memory_extractor is None:
            from app.core.agents.memory_extractor import MemoryExtractor
            self._memory_extractor = MemoryExtractor()
            self._register(
                "memory_extractor",
                "app.core.agents.memory_extractor",
                "MemoryExtractor",
            )
        return self._memory_extractor

    # ── Runtime State ──────────────────────────────────────────────────

    @property
    def state_manager(self) -> "StateManager":
        if self._state_manager is None:
            from app.core.runtime.state_manager import StateManager
            self._state_manager = StateManager()
            self._register(
                "state_manager", "app.core.runtime.state_manager", "StateManager",
            )
        return self._state_manager

    @property
    def runtime_config(self) -> "RuntimeConfig":
        if self._runtime_config is None:
            from app.core.runtime.runtime_config import RuntimeConfig
            self._runtime_config = RuntimeConfig()
            self._register(
                "runtime_config", "app.core.runtime.runtime_config", "RuntimeConfig",
            )
        return self._runtime_config

    # ── Legacy (not in inventory, backward compat only) ───────────────

    @property
    def task_engine(self) -> "TaskEngine":
        from app.core.runtime.task_engine import task_engine
        return task_engine

    @property
    def trigger_engine(self) -> "TriggerEngine":
        from app.core.runtime.trigger_engine import trigger_engine
        return trigger_engine

    # ── Lifecycle ──────────────────────────────────────────────────────

    # Property attribute names that hold cached singleton instances. Adding
    # a new subsystem property only requires appending its private attr here.
    _SINGLETON_ATTRS: tuple[str, ...] = (
        "_kernel",
        "_capability_governance",
        "_taint_registry",
        "_context_pipeline",
        "_fragment_registry",
        "_mcp_hub",
        "_llm_router",
        "_memory_engine",
        "_memory_extractor",
        "_state_manager",
        "_runtime_config",
    )

    def reset(self) -> None:
        """Reset all subsystem state — for test isolation.

        Drops every cached singleton so the next access rebuilds it from
        scratch, then clears module-level registries that live outside the
        container (taint tool sets, citation source registry, etc.).
        """
        with self._lock:
            # Drop cached instances — properties will lazily rebuild on access.
            for attr in self._SINGLETON_ATTRS:
                setattr(self, attr, None)
            self._inventory.clear()
            # Flush module-level registries that are not owned by the container.
            from app.core.runtime.governance.context_pipeline import reset_source_registry
            reset_source_registry()
            from app.core.runtime.taint import reset_external_tools
            reset_external_tools()


runtime = RuntimeContainer()

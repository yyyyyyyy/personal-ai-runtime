"""Runtime Container — centralized registry for Runtime subsystems.

Every subsystem singleton is accessible from a single container.
This enables single-point reset() for test isolation and future
multi-Kernel instances.

v0.5.0: All module-level singletons registered as lazy properties with
inventory tracking.  reset() clears all known subsystems.  Old module-level
imports still work (backward compatible) but new code should use runtime.x.

Architecture target: global singletons 15+ → 0 (all registered).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.context_runtime import FragmentRegistry
    from app.core.agents.llm_failover import LLMRouter
    from app.core.agents.memory_engine import MemoryEngine
    from app.core.agents.memory_extractor import MemoryExtractor
    from app.core.harness.mcp_hub import MCPHub
    from app.core.runtime.agent_bus import AgentBus
    from app.core.runtime.background_worker import BackgroundWorker
    from app.core.runtime.capability_governance import CapabilityGovernance
    from app.core.runtime.governance.context_pipeline import ContextPipeline
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.runtime_config import RuntimeConfig
    from app.core.runtime.state_manager import StateManager
    from app.core.runtime.taint import TaintRegistry
    from app.core.runtime.task_engine import TaskEngine
    from app.core.runtime.trigger_engine import TriggerEngine


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
        # messaging
        self._agent_bus: "AgentBus | None" = None
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
            from app.core.runtime.kernel_instance import kernel as k
            self._kernel = k
            self._register("kernel", "app.core.runtime.kernel_instance", type(k).__name__)
        return self._kernel

    @kernel.setter
    def kernel(self, value: "Kernel") -> None:
        self._kernel = value

    # ── Governance ─────────────────────────────────────────────────────

    @property
    def capability_governance(self) -> "CapabilityGovernance":
        if self._capability_governance is None:
            from app.core.runtime.capability_governance import capability_governance
            self._capability_governance = capability_governance
            self._register("capability_governance", "app.core.runtime.capability_governance", type(capability_governance).__name__)
        return self._capability_governance

    @property
    def taint_registry(self) -> "TaintRegistry":
        if self._taint_registry is None:
            from app.core.runtime.taint import taint_registry
            self._taint_registry = taint_registry
            self._register("taint_registry", "app.core.runtime.taint", type(taint_registry).__name__)
        return self._taint_registry

    # ── Messaging ──────────────────────────────────────────────────────

    @property
    def agent_bus(self) -> "AgentBus":
        if self._agent_bus is None:
            from app.core.runtime.agent_bus import agent_bus
            self._agent_bus = agent_bus
            self._register("agent_bus", "app.core.runtime.agent_bus", type(agent_bus).__name__)
        return self._agent_bus

    # ── Context ────────────────────────────────────────────────────────

    @property
    def context_pipeline(self) -> "ContextPipeline":
        if self._context_pipeline is None:
            from app.core.runtime.governance.context_pipeline import context_pipeline
            self._context_pipeline = context_pipeline
            self._register("context_pipeline", "app.core.runtime.governance.context_pipeline", type(context_pipeline).__name__)
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
            from app.core.harness.mcp_hub import mcp_hub as mh
            self._mcp_hub = mh
            self._register("mcp_hub", "app.core.harness.mcp_hub", type(mh).__name__)
        return self._mcp_hub

    # ── Agents / Memory ────────────────────────────────────────────────

    @property
    def llm_router(self) -> "LLMRouter":
        if self._llm_router is None:
            from app.core.agents.llm_failover import llm_router as lr
            self._llm_router = lr
            self._register("llm_router", "app.core.agents.llm_failover", type(lr).__name__)
        return self._llm_router

    @property
    def memory_engine(self) -> "MemoryEngine":
        if self._memory_engine is None:
            from app.core.agents.memory_engine import memory_engine as me
            self._memory_engine = me
            self._register("memory_engine", "app.core.agents.memory_engine", type(me).__name__)
        return self._memory_engine

    @property
    def memory_extractor(self) -> "MemoryExtractor":
        if self._memory_extractor is None:
            from app.core.agents.memory_extractor import memory_extractor as mx
            self._memory_extractor = mx
            self._register("memory_extractor", "app.core.agents.memory_extractor", type(mx).__name__)
        return self._memory_extractor

    # ── Runtime State ──────────────────────────────────────────────────

    @property
    def state_manager(self) -> "StateManager":
        if self._state_manager is None:
            from app.core.runtime.state_manager import state_manager as sm
            self._state_manager = sm
            self._register("state_manager", "app.core.runtime.state_manager", type(sm).__name__)
        return self._state_manager

    @property
    def runtime_config(self) -> "RuntimeConfig":
        if self._runtime_config is None:
            from app.core.runtime.runtime_config import runtime_config as rc
            self._runtime_config = rc
            self._register("runtime_config", "app.core.runtime.runtime_config", type(rc).__name__)
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

    @property
    def background_worker(self) -> "BackgroundWorker":
        from app.core.runtime.background_worker import background_worker
        return background_worker

    # ── Lifecycle ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all subsystem state — for test isolation.

        Always accesses properties to ensure the singleton is loaded,
        then calls reset() on it. This handles the case where tests
        use module-level imports but reset through the container.
        """
        with self._lock:
            self.agent_bus.reset()
            self.capability_governance.reset()
            from app.core.runtime.governance.context_pipeline import reset_source_registry
            reset_source_registry()
            from app.core.runtime.taint import reset_external_tools
            reset_external_tools()


runtime = RuntimeContainer()

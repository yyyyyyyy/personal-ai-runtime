"""Runtime Container — centralized registry for Runtime subsystems.

Every subsystem singleton is accessible from a single container.
This enables single-point reset() for test isolation and future
multi-Kernel instances.

Properties use direct singleton imports (no __import__ dynamic resolution)
to avoid circular import deadlocks. inventory() returns the authoritative
subsystem list, populated lazily on first access.

v0.4.0: CapabilityGateway + CapabilityPolicy + ApprovalEngine consolidated
into single CapabilityGovernance.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.runtime.agent_bus import AgentBus
    from app.core.runtime.background_worker import BackgroundWorker
    from app.core.runtime.capability_governance import CapabilityGovernance
    from app.core.runtime.governance.context_pipeline import ContextPipeline
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.taint import TaintRegistry
    from app.core.runtime.task_engine import TaskEngine
    from app.core.runtime.trigger_engine import TriggerEngine


class RuntimeContainer:
    """Holds all Runtime subsystem references for centralized lifecycle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._inventory: list[dict] = []
        self._kernel: "Kernel | None" = None
        self._capability_governance: "CapabilityGovernance | None" = None
        self._taint_registry: "TaintRegistry | None" = None
        self._agent_bus: "AgentBus | None" = None
        self._context_pipeline: "ContextPipeline | None" = None

    def inventory(self) -> list[dict]:
        """Return list of registered subsystems (lazily populated on first access)."""
        return list(self._inventory)

    # ── Kernel ───────────────────────────────────────────────────────

    @property
    def kernel(self) -> "Kernel":
        if self._kernel is None:
            from app.core.runtime.kernel_instance import kernel as k
            self._kernel = k
            self._inventory.append({"name": "kernel", "module": "app.core.runtime.kernel_instance", "class": type(k).__name__})
        return self._kernel

    @kernel.setter
    def kernel(self, value: "Kernel") -> None:
        self._kernel = value

    # ── Subsystem properties ──

    @property
    def capability_governance(self) -> "CapabilityGovernance":
        if self._capability_governance is None:
            from app.core.runtime.capability_governance import capability_governance
            self._capability_governance = capability_governance
            self._inventory.append({"name": "capability_governance", "module": "app.core.runtime.capability_governance", "class": type(capability_governance).__name__})
        return self._capability_governance

    @property
    def taint_registry(self) -> "TaintRegistry":
        if self._taint_registry is None:
            from app.core.runtime.taint import taint_registry
            self._taint_registry = taint_registry
            self._inventory.append({"name": "taint_registry", "module": "app.core.runtime.taint", "class": type(taint_registry).__name__})
        return self._taint_registry

    @property
    def agent_bus(self) -> "AgentBus":
        if self._agent_bus is None:
            from app.core.runtime.agent_bus import agent_bus
            self._agent_bus = agent_bus
            self._inventory.append({"name": "agent_bus", "module": "app.core.runtime.agent_bus", "class": type(agent_bus).__name__})
        return self._agent_bus

    @property
    def context_pipeline(self) -> "ContextPipeline":
        if self._context_pipeline is None:
            from app.core.runtime.governance.context_pipeline import context_pipeline
            self._context_pipeline = context_pipeline
            self._inventory.append({"name": "context_pipeline", "module": "app.core.runtime.governance.context_pipeline", "class": type(context_pipeline).__name__})
        return self._context_pipeline

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

    # ── Lifecycle ────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all subsystem state — for test isolation."""
        with self._lock:
            self.agent_bus.reset()
            self.capability_governance.reset()
            from app.core.runtime.governance.context_pipeline import reset_source_registry
            reset_source_registry()
            from app.core.runtime.taint import reset_external_tools
            reset_external_tools()


runtime = RuntimeContainer()

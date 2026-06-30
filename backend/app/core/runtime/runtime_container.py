"""Runtime Container — centralized registry for Runtime subsystems.

Every subsystem singleton is accessible from a single container.
This enables single-point reset() for test isolation and future
multi-Kernel instances.

Properties use direct singleton imports (no __import__ dynamic resolution)
to avoid circular import deadlocks. inventory() returns the authoritative
subsystem list, populated lazily on first access.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.runtime.agent_bus import AgentBus
    from app.core.runtime.approval_engine import ApprovalEngine
    from app.core.runtime.background_worker import BackgroundWorker
    from app.core.runtime.capability_decision import CapabilityGateway
    from app.core.runtime.capability_policy import CapabilityPolicy
    from app.core.runtime.event_bus import EventBus
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
        self._capability_gateway: "CapabilityGateway | None" = None
        self._capability_policy: "CapabilityPolicy | None" = None
        self._taint_registry: "TaintRegistry | None" = None
        self._agent_bus: "AgentBus | None" = None
        self._approval_engine: "ApprovalEngine | None" = None
        self._event_bus: "EventBus | None" = None
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

    # ── Subsystem properties (direct imports, no dynamic resolution) ──

    @property
    def capability_gateway(self) -> "CapabilityGateway":
        if self._capability_gateway is None:
            from app.core.runtime.capability_decision import capability_gateway
            self._capability_gateway = capability_gateway
            self._inventory.append({"name": "capability_gateway", "module": "app.core.runtime.capability_decision", "class": type(capability_gateway).__name__})
        return self._capability_gateway

    @property
    def capability_policy(self) -> "CapabilityPolicy":
        if self._capability_policy is None:
            from app.core.runtime.capability_policy import capability_policy
            self._capability_policy = capability_policy
            self._inventory.append({"name": "capability_policy", "module": "app.core.runtime.capability_policy", "class": type(capability_policy).__name__})
        return self._capability_policy

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
    def approval_engine(self) -> "ApprovalEngine":
        if self._approval_engine is None:
            from app.core.runtime.approval_engine import approval_engine
            self._approval_engine = approval_engine
            self._inventory.append({"name": "approval_engine", "module": "app.core.runtime.approval_engine", "class": type(approval_engine).__name__})
        return self._approval_engine

    @property
    def event_bus(self) -> "EventBus":
        if self._event_bus is None:
            from app.core.runtime.event_bus import event_bus
            self._event_bus = event_bus
            self._inventory.append({"name": "event_bus", "module": "app.core.runtime.event_bus", "class": type(event_bus).__name__})
        return self._event_bus

    @property
    def context_pipeline(self) -> "ContextPipeline":
        if self._context_pipeline is None:
            from app.core.runtime.governance.context_pipeline import context_pipeline
            self._context_pipeline = context_pipeline
            self._inventory.append({"name": "context_pipeline", "module": "app.core.runtime.governance.context_pipeline", "class": type(context_pipeline).__name__})
        return self._context_pipeline

    @property
    def task_engine(self) -> "TaskEngine":
        # Lazily loaded — not used in reset() path
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
            self.capability_policy.reset()
            from app.core.runtime.governance.context_pipeline import reset_source_registry
            reset_source_registry()
            from app.core.runtime.taint import reset_external_tools
            reset_external_tools()


runtime = RuntimeContainer()

"""Runtime Container — centralized registry for Runtime subsystems.

Every subsystem singleton (capability gateway, policy, taint, agent bus,
etc.) is accessible from a single container. This enables:

1. Single-point reset() for test isolation
2. Future multi-Kernel instances (one container per Kernel)
3. Backward compatibility: module-level singletons continue to work
   by lazily resolving from the container.

Architecture note (Phase 3 roadmap):
  This is a transitional pattern. The long-term goal is to inject each
  subsystem into Kernel.__init__ so every test creates its own instance.
  For now, this container provides 80% of the benefit with <5% of the
  migration effort.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.runtime.agent_bus import AgentBus
    from app.core.runtime.approval_engine import ApprovalEngine
    from app.core.runtime.capability_decision import CapabilityGateway
    from app.core.runtime.capability_policy import CapabilityPolicy
    from app.core.runtime.event_bus import EventBus
    from app.core.runtime.governance.context_pipeline import ContextPipeline
    from app.core.runtime.kernel.kernel import Kernel
    from app.core.runtime.taint import TaintRegistry


class RuntimeContainer:
    """Holds all Runtime subsystem references for centralized lifecycle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._kernel: "Kernel | None" = None
        self._capability_gateway: "CapabilityGateway | None" = None
        self._capability_policy: "CapabilityPolicy | None" = None
        self._taint_registry: "TaintRegistry | None" = None
        self._agent_bus: "AgentBus | None" = None
        self._approval_engine: "ApprovalEngine | None" = None
        self._event_bus: "EventBus | None" = None
        self._context_pipeline: "ContextPipeline | None" = None

    @property
    def kernel(self) -> "Kernel":
        if self._kernel is None:
            from app.core.runtime.kernel_instance import kernel as k
            self._kernel = k
        return self._kernel

    @kernel.setter
    def kernel(self, value: "Kernel") -> None:
        self._kernel = value

    @property
    def capability_gateway(self) -> "CapabilityGateway":
        if self._capability_gateway is None:
            from app.core.runtime.capability_decision import capability_gateway
            self._capability_gateway = capability_gateway
        return self._capability_gateway

    @property
    def capability_policy(self) -> "CapabilityPolicy":
        if self._capability_policy is None:
            from app.core.runtime.capability_policy import capability_policy
            self._capability_policy = capability_policy
        return self._capability_policy

    @property
    def taint_registry(self) -> "TaintRegistry":
        if self._taint_registry is None:
            from app.core.runtime.taint import taint_registry
            self._taint_registry = taint_registry
        return self._taint_registry

    @property
    def agent_bus(self) -> "AgentBus":
        if self._agent_bus is None:
            from app.core.runtime.agent_bus import agent_bus
            self._agent_bus = agent_bus
        return self._agent_bus

    @property
    def approval_engine(self) -> "ApprovalEngine":
        if self._approval_engine is None:
            from app.core.runtime.approval_engine import approval_engine
            self._approval_engine = approval_engine
        return self._approval_engine

    @property
    def event_bus(self) -> "EventBus":
        if self._event_bus is None:
            from app.core.runtime.event_bus import event_bus
            self._event_bus = event_bus
        return self._event_bus

    @property
    def context_pipeline(self) -> "ContextPipeline":
        if self._context_pipeline is None:
            from app.core.runtime.governance.context_pipeline import context_pipeline
            self._context_pipeline = context_pipeline
        return self._context_pipeline

    def reset(self) -> None:
        """Reset all subsystem state — for test isolation.

        Clears per-instance caches and registries without tearing down
        connections or projections. Safe to call between tests.
        """
        with self._lock:
            bus = self._agent_bus
            if bus is not None:
                bus.reset()
            policy = self._capability_policy
            if policy is not None:
                policy.reset()
            from app.core.runtime.governance.context_pipeline import reset_source_registry
            reset_source_registry()
            from app.core.runtime.taint import reset_external_tools
            reset_external_tools()


# Global singleton for backward compatibility
runtime = RuntimeContainer()

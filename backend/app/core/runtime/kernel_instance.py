"""Kernel singleton — the one and only entry point for User Space.

User-space code must never instantiate Kernel directly; it must import this
singleton. This is what enforces the GOLDEN RULE: User Space never touches
storage; everything goes through the kernel.

The concrete Kernel instance lives on RuntimeContainer; ``kernel`` here is a
lazy proxy that forwards every attribute access to ``runtime.kernel``. This
keeps ``from app.core.runtime.kernel_instance import kernel`` working while
making ``runtime.reset()`` the single point of test isolation.

Scheduler / execution helpers below are thin ABI wrappers so API and Product
do not import deep Runtime modules directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.runtime.runtime_container import _LazyProxy, runtime

if TYPE_CHECKING:
    from app.core.runtime.kernel.kernel import Kernel

if TYPE_CHECKING:
    kernel: "Kernel"
else:
    kernel = _LazyProxy(lambda: runtime.kernel)


async def ensure_runtime_scheduler() -> None:
    """Bind and start the process Scheduler if needed (API/Product ABI)."""
    from app.core.runtime.agent_scheduler import ensure_scheduler

    await ensure_scheduler(kernel)


def get_runtime_scheduler() -> Any:
    """Return the process Scheduler singleton (API/Product ABI)."""
    from app.core.runtime.agent_scheduler import get_scheduler

    return get_scheduler(kernel)


def get_current_execution_id() -> str | None:
    """Current Execution context id, if any (Product ABI)."""
    from app.core.runtime.execution import get_current_execution_id as _get

    return _get()


def bind_inbox_poll_applier(fn) -> None:
    """Register Product inbox poll applier on RuntimeContainer (ABI)."""
    from app.core.runtime.runtime_container import runtime

    runtime.bind_inbox_poll_applier(fn)

"""Kernel singleton — the one and only entry point for User Space.

User-space code must never instantiate Kernel directly; it must import this
singleton. This is what enforces the GOLDEN RULE: User Space never touches
storage; everything goes through the kernel.

The concrete Kernel instance lives on RuntimeContainer; ``kernel`` here is a
lazy proxy that forwards every attribute access to ``runtime.kernel``. This
keeps ``from app.core.runtime.kernel_instance import kernel`` working while
making ``runtime.reset()`` the single point of test isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.runtime.runtime_container import _LazyProxy, runtime

if TYPE_CHECKING:
    from app.core.runtime.kernel.kernel import Kernel

if TYPE_CHECKING:
    kernel: "Kernel"
else:
    kernel = _LazyProxy(lambda: runtime.kernel)

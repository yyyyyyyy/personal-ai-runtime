"""Kernel singleton — the one and only entry point for User Space.

User-space code must never instantiate Kernel directly; it must import this
singleton. This is what enforces the GOLDEN RULE: User Space never touches
storage; everything goes through the kernel.
"""

from app.core.runtime.kernel import Kernel

kernel = Kernel()

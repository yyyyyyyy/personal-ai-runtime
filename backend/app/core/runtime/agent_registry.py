"""Agent registry — minimal stub (was: full Agent lifecycle manager).

v0.4.0: Agent lifecycle removed. This stub exists only for backward compat
with kernel.metrics() and runtime_loop's cleanup_stale call.
"""
from __future__ import annotations


class AgentRegistry:
    """Minimal stub — no Agent instances are spawned in single-user mode."""

    def __init__(self, kernel):
        self._kernel = kernel

    def get(self, instance_id: str):
        return None

    def __len__(self) -> int:
        return 0

    async def cleanup_stale(self, max_age_seconds: int | None = None) -> list[str]:
        return []

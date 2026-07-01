"""Timer Engine — cron schedule registration and management.

v0.3.0: The scanning loop moved to RuntimeLoop.  This module retains
the public API: ensure_schedules / create_schedule / list_schedules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_loop import RuntimeLoop

if TYPE_CHECKING:
    from app.core.runtime.kernel.kernel import Kernel

logger = logging.getLogger(__name__)


class TimerEngine:
    """Cron schedule registration and management.

    The scanning loop (check-and-fire) is now driven by RuntimeLoop._check_timers().
    """

    def __init__(self, _kernel: Kernel):
        self._kernel = _kernel

    def ensure_schedules(self, schedules: list[dict]) -> None:
        """Ensure timer projections exist for the given schedule definitions.

        Called at startup to register timers from scheduler config.
        Each schedule dict: {name, cron_expr, schedule_type, handler_name}
        """
        for sched in schedules:
            name = sched["name"]
            existing = kernel.query_state("timer_events", id=name, limit=1)
            if existing:
                continue
            cron_expr = sched.get("cron_expr", "")
            next_fire = RuntimeLoop._next_cron_fire(cron_expr)
            kernel.emit_event(
                "TimerCreated", "timer", name,
                payload={
                    "handler_name": sched.get("handler_name", ""),
                    "schedule_type": sched.get("schedule_type", "cron"),
                    "cron_expr": cron_expr,
                    "fire_at": next_fire,
                },
                actor="system",
            )

    def create_schedule(
        self, name: str, handler_name: str, cron_expr: str, schedule_type: str = "cron",
    ) -> str:
        """Create a new timer schedule."""
        next_fire = RuntimeLoop._next_cron_fire(cron_expr)
        kernel.emit_event(
            "TimerCreated", "timer", name,
            payload={
                "handler_name": handler_name,
                "schedule_type": schedule_type,
                "cron_expr": cron_expr,
                "fire_at": next_fire,
            },
            actor="system",
        )
        return name

    def list_schedules(self) -> list[dict]:
        """List all registered timer schedules."""
        return kernel.query_state("timer_events", limit=500)

    def delete_schedule(self, name: str) -> None:
        rows = kernel.query_state("timer_events", id=name, limit=1)
        if rows:
            kernel.emit_event("TimerCancelled", "timer", name, actor="system")


timer_engine = TimerEngine(kernel)

# Backward-compatible alias for tests
_next_cron_fire = RuntimeLoop._next_cron_fire

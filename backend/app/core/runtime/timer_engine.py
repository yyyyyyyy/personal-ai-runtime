"""Timer schedule registration — unified with RuntimeLoop scanning.

v0.3.0: The scanning loop moved to RuntimeLoop.
The TimerEngine class has been removed; schedule CRUD is now functional
wrappers around Kernel ABI (emit_event / query_state).

Static utility _next_cron_fire remains for RuntimeLoop use.
"""

from __future__ import annotations

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_loop import RuntimeLoop

# Re-export for backward compat
_next_cron_fire = RuntimeLoop._next_cron_fire


def ensure_schedules(schedules: list[dict]) -> None:
    """Ensure timer projections exist for the given schedule definitions."""
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

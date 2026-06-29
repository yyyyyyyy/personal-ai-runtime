"""Timer Engine — Runtime's time dimension.

Replaces APScheduler's runtime role. Scans the timer_events projection
every second and emits TimerFired events when timers are due.

APScheduler is retained only as a startup-compatible fallback (target:
remove entirely). The Timer Engine is the authoritative time source:
    TimerCreated → projection → engine scan → TimerFired → handler → ExecutionRequested

Cron evaluation: supports the 12 cron patterns used by the existing scheduler
(hour/minute/day_of_week/day without croniter dependency).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.runtime.kernel.kernel import Kernel

logger = logging.getLogger(__name__)

_SCAN_INTERVAL = 1.0  # seconds between projection scans


def _next_cron_fire(cron_expr: str, from_ts: datetime | None = None) -> str:
    """Calculate the next fire time for a simple cron expression.

    Supports patterns used in this project:
      - hour=H, minute=M
      - day_of_week=D, hour=H, minute=M
      - day=D, hour=H, minute=M
      - minute=*/N (every N minutes)

    Returns ISO 8601 string.
    """
    now = from_ts or datetime.now(UTC)
    parts = {p.split("=")[0].strip(): p.split("=")[1].strip() for p in cron_expr.split(",")}

    if "minute" in parts and parts["minute"].startswith("*/"):
        interval = int(parts["minute"][2:])
        # Start from beginning of current interval block
        current_block = (now.minute // interval) * interval
        next_minute = current_block + interval
        if next_minute >= 60:
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return (next_time + timedelta(minutes=next_minute - 60)).isoformat()
        next_time = now.replace(minute=next_minute, second=0, microsecond=0)
        if next_time <= now:
            next_time += timedelta(minutes=interval)
        return next_time.isoformat()

    hour = int(parts.get("hour", "0"))
    minute = int(parts.get("minute", "0"))

    # Day-specific patterns
    if "day" in parts:
        day = int(parts["day"])
        next_time = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        if next_time <= now:
            if now.month == 12:
                next_time = now.replace(year=now.year + 1, month=1, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            else:
                next_time = now.replace(month=now.month + 1, day=day, hour=hour, minute=minute, second=0, microsecond=0)
        return next_time.isoformat()

    if "day_of_week" in parts:
        target_dow = parts["day_of_week"]
        dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target = dow_map.get(target_dow, 0)
        days_ahead = target - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_time = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return next_time.isoformat()

    # default: daily at H:M
    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_time <= now:
        next_time += timedelta(days=1)
    return next_time.isoformat()


class TimerEngine:
    """Runtime-level timer engine — owns the time dimension.

    Scans the timer_events projection for active timers whose fire_at
    has passed, and emits TimerFired events.
    """

    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("TimerEngine started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TimerEngine stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_and_fire()
            except Exception:
                logger.exception("TimerEngine scan error")
            await asyncio.sleep(_SCAN_INTERVAL)

    async def _check_and_fire(self) -> None:
        """Scan active timers and fire any that are due."""
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        rows = self._kernel.query_state(
            "timer_events",
            status="active",
            fire_at_lt=now_iso,
            limit=50,
        )

        for row in rows:
            timer_id = row["id"]
            handler_name = row.get("handler_name", "")
            cron_expr = row.get("cron_expr", "")
            schedule_type = row.get("schedule_type", "cron")

            if not handler_name:
                continue

            # Emit TimerFired — "the future has happened"
            self._kernel.emit_event(
                "TimerFired",
                "timer",
                timer_id,
                payload={
                    "handler_name": handler_name,
                    "fired_at": now_iso,
                    "cron_expr": cron_expr,
                },
                actor="timer_engine",
            )

            # For cron timers: recalculate next fire_at and re-create
            if schedule_type == "cron" and cron_expr:
                next_fire = _next_cron_fire(cron_expr, now)
                new_timer_id = f"t_{uuid.uuid4().hex[:12]}"
                self._kernel.emit_event(
                    "TimerCreated",
                    "timer",
                    new_timer_id,
                    payload={
                        "handler_name": handler_name,
                        "schedule_type": "cron",
                        "cron_expr": cron_expr,
                        "fire_at": next_fire,
                    },
                    actor="timer_engine",
                )

    def ensure_schedules(self, schedules: list[dict]) -> None:
        """Ensure timer projections exist for the given schedule definitions.

        Called at startup to register timers from scheduler config.
        Each schedule dict: {name, cron_expr, schedule_type, handler_name}
        """
        for sched in schedules:
            name = sched["name"]
            existing = self._kernel.query_state("timer_events", id=name, limit=1)
            if existing:
                continue
            cron_expr = sched.get("cron_expr", "")
            fire_at = _next_cron_fire(cron_expr)
            self._kernel.emit_event(
                "TimerCreated",
                "timer",
                name,
                payload={
                    "handler_name": sched.get("handler_name", name),
                    "schedule_type": sched.get("schedule_type", "cron"),
                    "cron_expr": cron_expr,
                    "delay_seconds": float(sched.get("delay_seconds", 0)),
                    "fire_at": fire_at,
                },
                actor="timer_engine",
            )


# Global singleton
_timer_engine: TimerEngine | None = None


def get_timer_engine(kernel: Kernel) -> TimerEngine:
    global _timer_engine
    if _timer_engine is None:
        _timer_engine = TimerEngine(kernel)
    return _timer_engine


def reset_timer_engine() -> None:
    global _timer_engine
    _timer_engine = None


def get_current_timer_engine() -> TimerEngine | None:
    """Return the current TimerEngine singleton without creating one."""
    return _timer_engine

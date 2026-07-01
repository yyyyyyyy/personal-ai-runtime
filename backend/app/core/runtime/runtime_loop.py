"""RuntimeLoop — unified runtime scheduler replacing TimerEngine+BackgroundWorker loops.

Single asynchronous loop with a 100ms tick, two maintenance tiers:
  - Every 10 ticks (~1s): Timer scan (ex-timer_engine)
  - Every 100 ticks (~10s): Background maintenance (ex-background_worker polling)

The agent_scheduler still drives WorkItem execution independently (its start/stop
lifecycle is triggered by chat API calls). RuntimeLoop focuses on the
autonomous background loops.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)

_TICK_SECONDS = 0.1        # main tick interval
_TIMER_EVERY = 10          # timer scan every N ticks (~1s)
_MAINT_EVERY = 100         # maintenance every N ticks (~10s)


class RuntimeLoop:
    """Unified runtime loop — drives timer scanning and background maintenance.

    Architecture:
        RuntimeLoop._tick()
          ├── _check_timers()        ← ex-TimerEngine loop (every 10 ticks)
          └── _maintenance()         ← ex-BackgroundWorker loop (every 100 ticks)
    """

    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._tick_count = 0

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop())
        logger.info("RuntimeLoop started (tick=%.0fms)", _TICK_SECONDS * 1000)

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("RuntimeLoop stopped")

    # ── main loop ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("RuntimeLoop tick error")
            await asyncio.sleep(_TICK_SECONDS)

    async def _tick(self) -> None:
        self._tick_count += 1

        if self._tick_count % _TIMER_EVERY == 0:
            await self._check_timers()

        if self._tick_count % _MAINT_EVERY == 0:
            await self._maintenance()

        # Prevent overflow for long-running processes
        if self._tick_count > 10_000_000:
            self._tick_count = 0

    # ── Timer scan ────────────────────────────────────────────────────

    async def _check_timers(self) -> None:
        """Scan timer_events projection, fire due timers (ex-timer_engine)."""
        from datetime import UTC, datetime

        try:
            now = datetime.now(UTC)
            now_iso = now.isoformat()
            rows = kernel.query_state(
                "timer_events", status="active", fire_at_lt=now_iso, limit=50,
            )
            for row in rows:
                timer_id = row["id"]
                handler_name = row.get("handler_name", "")
                cron_expr = row.get("cron_expr", "")
                schedule_type = row.get("schedule_type", "cron")
                if not handler_name:
                    continue
                kernel.emit_event(
                    "TimerFired", "timer", timer_id,
                    payload={
                        "handler_name": handler_name,
                        "fired_at": now_iso,
                        "cron_expr": cron_expr,
                    },
                    actor="runtime_loop",
                )
                if schedule_type == "cron" and cron_expr:
                    next_fire = self._next_cron_fire(cron_expr, now)
                    new_tid = f"t_{__import__('uuid').uuid4().hex[:12]}"
                    kernel.emit_event(
                        "TimerCreated", "timer", new_tid,
                        payload={
                            "handler_name": handler_name,
                            "schedule_type": "cron",
                            "cron_expr": cron_expr,
                            "fire_at": next_fire,
                        },
                        actor="runtime_loop",
                    )
        except Exception:
            logger.exception("RuntimeLoop timer scan error")

    @staticmethod
    def _next_cron_fire(cron_expr: str, from_ts=None) -> str:
        """Calculate the next fire time for a cron expression."""
        from datetime import UTC, datetime, timedelta

        now = from_ts or datetime.now(UTC)
        parts = {p.split("=")[0].strip(): p.split("=")[1].strip() for p in cron_expr.split(",")}

        if "minute" in parts and parts["minute"].startswith("*/"):
            interval = int(parts["minute"][2:])
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
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if "day" in parts:
            target = target.replace(day=int(parts["day"]))
        elif "day_of_week" in parts:
            # Support both numeric (0=Mon) and name ("mon", "monday")
            dow_str = parts["day_of_week"].lower()
            _DOW_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                        "friday": 4, "saturday": 5, "sunday": 6}
            dow = _DOW_MAP.get(dow_str, 0)
            try:
                dow = int(dow_str)
            except ValueError:
                pass
            days_ahead = dow - target.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target += timedelta(days=days_ahead)
        if target <= now:
            if "day" in parts or "day_of_week" in parts:
                target += timedelta(days=1) if "day" not in parts else timedelta(days=31)
                target = target.replace(day=1)
            else:
                target += timedelta(days=1)
        return target.isoformat()

    # ── Background maintenance ─────────────────────────────────────────

    async def _maintenance(self) -> None:
        """Background maintenance (ex-background_worker polling)."""
        try:
            await kernel.agent_registry.cleanup_stale()
        except Exception:
            logger.exception("Agent cleanup failed")

        try:
            expired = kernel.expire_stale_approvals()
            if expired:
                logger.info("Expired %d stale approval(s)", expired)
        except Exception:
            logger.exception("Approval expiry failed")

        try:
            await self._smart_notification_check()
        except Exception:
            logger.exception("Smart notification check failed")

        try:
            await self._process_background_tasks()
        except Exception:
            logger.exception("Background task processing failed")

    async def _smart_notification_check(self) -> None:
        """Check for stagnant goals, create notifications."""
        from datetime import UTC, datetime

        stagnant_goals = kernel.query_state(
            "goals", status="active", last_activity_older_than_days=3,
            order="last_activity_asc", limit=5,
        )
        for goal in stagnant_goals:
            goal_id = goal.get("id", "")
            title = goal.get("title", "")
            last_activity = goal.get("last_activity_at") or goal.get("created_at", "")
            existing = kernel.query_state(
                "notifications", related_id=goal_id,
                notification_type="goal_stagnant", limit=1,
            )
            if existing:
                notif_time = existing[0].get("created_at", "")
                if notif_time > last_activity:
                    continue
            try:
                activity_dt = datetime.fromisoformat(last_activity)
                days_stagnant = (datetime.now(UTC) - activity_dt).days
            except (ValueError, TypeError):
                days_stagnant = 3
            kernel.emit_event(
                "NotificationCreated", "notification", f"notif_stagnant_{goal_id}",
                payload={
                    "type": "goal_stagnant",
                    "title": f"目标停滞: {title}",
                    "content": f"目标已 {days_stagnant} 天未更新，需要关注",
                    "severity": "warning",
                    "related_id": goal_id,
                    "related_type": "goal",
                    "notification_type": "goal_stagnant",
                },
                actor="system",
            )
            logger.info("Created stagnant goal notification for: %s", title)

    async def _process_background_tasks(self) -> None:
        """Process pending background tasks."""
        from app.core.runtime.agent_bootstrap import ensure_agent
        from app.core.runtime.agent_scheduler import get_scheduler
        from app.core.runtime.kernel.constants import (
            AGGREGATE_BACKGROUND_TASK,
            EVENT_BG_TASK_STATUS_CHANGED,
        )

        rows = kernel.query_state(
            "background_tasks", status="pending", limit=1, order="created_at_asc",
        )
        for row in rows:
            task_id = row["id"]
            plan_json = row.get("plan_json", "{}")
            kernel.emit_event(
                EVENT_BG_TASK_STATUS_CHANGED, AGGREGATE_BACKGROUND_TASK,
                f"bg_{task_id}",
                payload={"task_id": task_id, "status": "running", "progress": 0.1},
                actor="background",
            )
            await ensure_agent(kernel)
            sch = get_scheduler(kernel)
            await sch.start()
            await kernel.submit_command(
                "BackgroundTaskRequested", AGGREGATE_BACKGROUND_TASK,
                f"bg_{task_id}",
                payload={"task_id": task_id, "plan_json": plan_json, "replan_count": 0},
                actor="background", timeout=120.0,
            )


runtime_loop = RuntimeLoop()

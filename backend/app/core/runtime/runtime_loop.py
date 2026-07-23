"""RuntimeLoop — unified runtime scheduler replacing TimerEngine+BackgroundWorker loops.

Single asynchronous loop with a 100ms tick, two maintenance tiers:
  - Every 10 ticks (~1s): Timer scan (ex-timer_engine)
  - Every 100 ticks (~10s): Background maintenance (ex-background_worker polling)

Blocking maintenance operations (ChromaDB repair, reaction evaluation) are
offloaded to a worker thread via asyncio.to_thread so they never stall the
event loop. Background task dispatch is fire-and-forget so the long
submit_command timeout cannot block timer scans or approval expiry.

The agent_scheduler still drives WorkItem execution independently (its start/stop
lifecycle is triggered by chat API calls). RuntimeLoop focuses on the
autonomous background loops.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Coroutine

from app.config import settings
from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_container import _LazyProxy, runtime

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
        self._dirty = False  # set by reset() when event loop changes
        # Fire-and-forget background tasks. Held to prevent GC and to allow
        # graceful cancellation on stop(). See _spawn_background_task.
        self._bg_tasks: set[asyncio.Task] = set()

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        # When reset() marked us dirty (previous event loop closed),
        # clean up the zombie task so create_task won't fail on a dead loop.
        if self._dirty:
            self._loop_task = None
            self._running = False
            self._dirty = False
        if self._running:
            return
        self._running = True
        recovered = self._recover_interrupted_background_tasks()
        if recovered:
            logger.info(
                "RuntimeLoop: re-queued %d interrupted background task(s)",
                recovered,
            )
        self._loop_task = asyncio.create_task(self._loop())
        try:
            from app.core.runtime.notification_bridge import set_broadcast_loop

            set_broadcast_loop(asyncio.get_running_loop())
        except Exception:
            logger.debug("Could not bind notification broadcast loop", exc_info=True)
        logger.info("RuntimeLoop started (tick=%.0fms)", _TICK_SECONDS * 1000)

    async def stop(self) -> None:
        self._running = False
        try:
            from app.core.runtime.notification_bridge import set_broadcast_loop

            set_broadcast_loop(None)
        except Exception:
            pass
        if self._loop_task:
            try:
                self._loop_task.cancel()
                await self._loop_task
            except (asyncio.CancelledError, RuntimeError):
                # RuntimeError = "no running event loop". Happens when
                # the old event loop was already shut down (e.g. between
                # TestClient instances in pytest). In that case we just
                # clear the zombie task — there is nothing to await.
                pass
            finally:
                self._loop_task = None
        # Cancel fire-and-forget background dispatches so start() recovery
        # cannot double-submit alongside a surviving coroutine.
        pending_bg = list(self._bg_tasks)
        for task in pending_bg:
            task.cancel()
        if pending_bg:
            await asyncio.gather(*pending_bg, return_exceptions=True)
        self._bg_tasks.clear()
        logger.info("RuntimeLoop stopped")

    def mark_dirty(self) -> None:
        """Mark the loop as needing cleanup on next start() (synchronous).

        Call this from ``RuntimeContainer.reset()`` when the event loop has
        changed. The actual zombie-task cleanup is deferred to the next
        ``start()`` call (which must be async), so ``reset`` stays
        synchronous.
        """
        self._dirty = True

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
            now_iso = now.isoformat().replace("+00:00", "Z")
            rows = read_ports.query_due_timers(now_iso=now_iso, limit=50)
            for row in rows:
                timer_id = row["id"]
                handler_name = row.get("handler_name", "")
                cron_expr = row.get("cron_expr", "")
                schedule_type = row.get("schedule_type", "cron")
                payload_json = row.get("payload_json") or "{}"

                try:
                    payload = json.loads(payload_json)
                except Exception:
                    payload = {}

                if not handler_name:
                    continue
                kernel.emit_event(
                    "TimerFired", "timer", timer_id,
                    payload={
                        "handler_name": handler_name,
                        "fired_at": now_iso,
                        "cron_expr": cron_expr,
                        "payload": payload,
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
                            "payload": payload,
                        },
                        actor="runtime_loop",
                    )
        except Exception:
            logger.exception("RuntimeLoop timer scan error")

    @staticmethod
    def _next_cron_fire(cron_expr: str, from_ts=None) -> str:
        """Calculate the next fire time for a cron expression."""
        from datetime import UTC, datetime, timedelta, tzinfo
        from zoneinfo import ZoneInfo

        try:
            tz: tzinfo = ZoneInfo(settings.timezone)
        except Exception:
            tz = UTC

        # We calculate the target in the user's local timezone
        now_local = from_ts or datetime.now(tz)
        # Ensure now_local is aware and in the right TZ if from_ts was passed
        if now_local.tzinfo is None:
            now_local = now_local.replace(tzinfo=UTC).astimezone(tz)
        elif now_local.tzinfo != tz:
            now_local = now_local.astimezone(tz)

        parts = {p.split("=")[0].strip(): p.split("=")[1].strip() for p in cron_expr.split(",")}

        if "minute" in parts and parts["minute"].startswith("*/"):
            interval = int(parts["minute"][2:])
            current_block = (now_local.minute // interval) * interval
            next_minute = current_block + interval
            if next_minute >= 60:
                next_time = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                res_dt = next_time + timedelta(minutes=next_minute - 60)
                return res_dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
            res_dt = now_local.replace(minute=next_minute, second=0, microsecond=0)
            if res_dt <= now_local:
                res_dt += timedelta(minutes=interval)
            return res_dt.astimezone(UTC).isoformat().replace("+00:00", "Z")

        hour = int(parts.get("hour", "0"))
        minute = int(parts.get("minute", "0"))
        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
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
        if target <= now_local:
            if "day" in parts or "day_of_week" in parts:
                target += timedelta(days=1) if "day" not in parts else timedelta(days=31)
                target = target.replace(day=1)
            else:
                target += timedelta(days=1)

        # Always return as UTC ISO8601 for consistent string comparison in DB
        return target.astimezone(UTC).isoformat().replace("+00:00", "Z")

    # ── Background maintenance ─────────────────────────────────────────

    async def _maintenance(self) -> None:
        """Background maintenance (ex-background_worker polling).

        Blocking operations (ChromaDB indexing, SQLite-heavy reaction
        evaluation) are offloaded to a worker thread via asyncio.to_thread
        so they never stall the event loop. Background task dispatch is
        fire-and-forget so the 300s submit_command timeout cannot block
        timer scans or approval expiry.
        """
        try:
            expired = kernel.expire_stale_approvals()
            if expired:
                logger.info("Expired %d stale approval(s)", expired)
        except Exception:
            logger.exception("Approval expiry failed")

        try:
            await self._check_reactions()
        except Exception:
            logger.exception("Reaction evaluation failed")

        try:
            await self._process_background_tasks()
        except Exception:
            logger.exception("Background task processing failed")

        try:
            await asyncio.to_thread(self._drain_memory_index_repairs)
        except Exception:
            logger.exception("Memory index repair worker failed")

    def _drain_memory_index_repairs(self) -> None:
        """Delegate durable repair drain to Kernel ABI (no private ``_db``)."""
        kernel.drain_memory_index_repairs()

    async def _check_reactions(self) -> None:
        """Evaluate registered Reactions.

        Offloaded to a worker thread because evaluate_cycle performs
        synchronous SQLite reads/writes that can block the event loop.
        """
        from app.core.runtime.reaction_registry import get_reaction_registry

        registry = get_reaction_registry()
        await asyncio.to_thread(registry.evaluate_cycle, kernel)

    # --- Backward compat (kept for the staleness reaction path) ----------------

    def _recover_interrupted_background_tasks(self) -> int:
        """Reset durable ``running`` background tasks to ``pending`` after restart.

        RuntimeLoop marks rows ``running`` before fire-and-forget dispatch.
        Process death / shutdown cancel leaves them stuck: maintenance only
        polls ``pending``, and Lane A ``Scheduler._recover`` does **not**
        touch ``background_tasks``. Re-queue via status event so the next
        maintenance tick can dispatch again (at-least-once).

        ``waiting_approval`` is left alone (plan_resume + approval still apply).
        """
        from app.core.runtime.kernel.constants import (
            AGGREGATE_BACKGROUND_TASK,
            EVENT_BG_TASK_STATUS_CHANGED,
        )

        try:
            rows = read_ports.query_background_tasks(
                status="running", limit=100, order="created_at_asc",
            )
        except Exception:
            logger.exception("Background task recovery scan failed")
            return 0

        recovered = 0
        for row in rows:
            task_id = row["id"]
            try:
                kernel.emit_event(
                    EVENT_BG_TASK_STATUS_CHANGED,
                    AGGREGATE_BACKGROUND_TASK,
                    f"bg_{task_id}",
                    payload={
                        "task_id": task_id,
                        "status": "pending",
                        "progress": float(row.get("progress") or 0),
                        "recovery": "interrupted",
                    },
                    actor="kernel",
                )
                recovered += 1
            except Exception:
                logger.exception(
                    "Failed to re-queue interrupted background task %s", task_id
                )
        return recovered

    async def _process_background_tasks(self) -> None:
        """Process pending background tasks.

        Dispatch is fire-and-forget: the submit_command call (which may take
        up to 300s) runs in a background task so it never blocks the
        maintenance tick. The completion event resolves the command future
        asynchronously via _dispatch, independent of this method returning.
        """
        from app.core.runtime.agent_scheduler import ensure_scheduler, get_scheduler
        from app.core.runtime.kernel.constants import (
            AGGREGATE_BACKGROUND_TASK,
            EVENT_BG_TASK_COMPLETED,
            EVENT_BG_TASK_STATUS_CHANGED,
        )

        rows = read_ports.query_background_tasks(
            status="pending", limit=1, order="created_at_asc",
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
            await ensure_scheduler(kernel)
            sch = get_scheduler(kernel)
            await sch.start()

            async def _dispatch_bg(t_id: str, pj: str) -> None:
                try:
                    await kernel.submit_command(
                        "BackgroundTaskRequested", AGGREGATE_BACKGROUND_TASK,
                        f"bg_{t_id}",
                        payload={"task_id": t_id, "plan_json": pj, "replan_count": 0},
                        actor="background",
                        timeout=settings.submit_command_timeout_background_task,
                    )
                except asyncio.CancelledError:
                    # Shutdown cancel: leave row as running; start() recovery
                    # re-queues it as pending on next process boot.
                    raise
                except Exception:
                    logger.exception("Background task %s failed", t_id)
                    try:
                        kernel.emit_event(
                            EVENT_BG_TASK_COMPLETED,
                            AGGREGATE_BACKGROUND_TASK,
                            f"bg_{t_id}",
                            payload={
                                "task_id": t_id,
                                "status": "failed",
                                "progress": 0.0,
                                "error": "dispatch_failed",
                            },
                            actor="background",
                        )
                    except Exception:
                        logger.exception(
                            "Failed to mark background task %s as failed", t_id
                        )

            self._spawn_background_task(_dispatch_bg(task_id, plan_json))

    def _spawn_background_task(self, coro: Coroutine[Any, Any, None]) -> None:
        """Create a tracked fire-and-forget task.

        The task reference is held in _bg_tasks to prevent the GC from
        collecting it mid-flight (a known asyncio footgun when create_task
        results are discarded). On completion the entry is discarded.
        """
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)


runtime_loop = _LazyProxy(lambda: runtime.runtime_loop)


def reset_runtime_loop() -> None:
    """Mark the runtime_loop singleton as dirty (test isolation).

    The loop holds ``_loop_task: asyncio.Task`` bound to whichever event
    loop was active at ``start()`` time. When the event loop changes
    (e.g. between TestClient requests), ``start()`` would see
    ``_running=True`` and short-circuit, leaving no tick in the new
    loop. ``mark_dirty()`` is synchronous (no await needed), so it can
    be called from ``RuntimeContainer.reset()``; the actual cleanup
    happens lazily on the next ``start()`` call.
    """
    from app.core.runtime.runtime_container import runtime

    if runtime._runtime_loop is not None:
        runtime._runtime_loop.mark_dirty()

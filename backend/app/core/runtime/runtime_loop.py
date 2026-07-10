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
import logging

from app.config import settings
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
        self._dirty = False  # v0.3.0: set by reset() when event loop changes

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        # v0.3.0: when reset() marked us dirty (previous event loop closed),
        # clean up the zombie task so create_task won't fail on a dead loop.
        if self._dirty:
            self._loop_task = None
            self._running = False
            self._dirty = False
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop())
        logger.info("RuntimeLoop started (tick=%.0fms)", _TICK_SECONDS * 1000)

    async def stop(self) -> None:
        self._running = False
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
        """Re-attempt ChromaDB index syncs that previously failed.

        Pulls a bounded batch of pending rows from memory_index_repairs,
        retries each one, and either deletes the row (success) or bumps
        retry_count. Rows that exceed the retry budget are marked
        'failed_permanent' and emit a MemoryIndexRepairFailed event so the
        operator (and eventually the UI) can see which memories are not
        recallable.
        """
        from datetime import UTC, datetime

        from app.core.runtime.kernel.constants import (
            EVENT_MEMORY_INDEX_REPAIR_FAILED,
            EVENT_MEMORY_UPDATED,
        )

        if kernel._memory_index is None:
            return

        max_retries = 5
        batch_size = 10
        now_iso = datetime.now(UTC).isoformat()
        db = kernel._db

        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, aggregate_id, event_type, event_seq, retry_count "
                "FROM memory_index_repairs "
                "WHERE status = 'pending' AND retry_count < ? "
                "ORDER BY id ASC LIMIT ?",
                (max_retries, batch_size),
            ).fetchall()

        for row in rows:
            repair_id = row["id"]
            aggregate_id = row["aggregate_id"]
            event_type = row["event_type"]

            # MemoryDeleted repairs only need a delete; everything else needs re-index.
            try:
                if event_type == "MemoryDeleted":
                    kernel._memory_index.delete_memory(aggregate_id)
                else:
                    # Pull current memory content from projection.
                    mem_rows = kernel.query_state("memories", id=aggregate_id, limit=1)
                    if not mem_rows:
                        # Memory was deleted after the failure; nothing to index.
                        with db.get_db() as conn:
                            conn.execute(
                                "DELETE FROM memory_index_repairs WHERE id = ?",
                                (repair_id,),
                            )
                        continue
                    mem = mem_rows[0]
                    content = str(mem.get("content", ""))
                    if not content:
                        with db.get_db() as conn:
                            conn.execute(
                                "DELETE FROM memory_index_repairs WHERE id = ?",
                                (repair_id,),
                            )
                        continue
                    embedding_id = kernel._memory_index.index_memory(
                        content=content,
                        metadata={
                            "category": str(mem.get("category", "general")),
                            "source": str(mem.get("source", "")),
                        },
                        memory_id=aggregate_id,
                    )
                    # Backfill embedding_id into the projection if still missing.
                    if not mem.get("embedding_id") and embedding_id:
                        kernel.emit_event(
                            EVENT_MEMORY_UPDATED, "memory", aggregate_id,
                            payload={"embedding_id": embedding_id},
                            actor="kernel",
                        )
                with db.get_db() as conn:
                    conn.execute(
                        "DELETE FROM memory_index_repairs WHERE id = ?",
                        (repair_id,),
                    )
                logger.info(
                    "Memory index repair succeeded for %s (event_seq=%s)",
                    aggregate_id, row["event_seq"],
                )
            except Exception as exc:
                new_count = row["retry_count"] + 1
                if new_count >= max_retries:
                    with db.get_db() as conn:
                        conn.execute(
                            "UPDATE memory_index_repairs "
                            "SET retry_count = ?, status = 'failed_permanent', "
                            "    last_retry_at = ?, error = ? "
                            "WHERE id = ?",
                            (new_count, now_iso, str(exc)[:500], repair_id),
                        )
                    kernel.emit_event(
                        EVENT_MEMORY_INDEX_REPAIR_FAILED, "memory", aggregate_id,
                        payload={
                            "aggregate_id": aggregate_id,
                            "event_seq": row["event_seq"],
                            "retry_count": new_count,
                            "error": str(exc)[:500],
                        },
                        actor="kernel",
                    )
                    logger.error(
                        "Memory index repair permanently failed for %s after "
                        "%d attempts — memory will not be recallable until "
                        "verify_vector_consistency.py reconciles it",
                        aggregate_id, new_count,
                        exc_info=True,
                    )
                else:
                    with db.get_db() as conn:
                        conn.execute(
                            "UPDATE memory_index_repairs "
                            "SET retry_count = ?, last_retry_at = ?, error = ? "
                            "WHERE id = ?",
                            (new_count, now_iso, str(exc)[:500], repair_id),
                        )
                    logger.warning(
                        "Memory index repair retry %d/%d for %s: %s",
                        new_count, max_retries, aggregate_id, exc,
                    )

    async def _check_reactions(self) -> None:
        """Evaluate registered Reactions (v0.6.0: replaces TriggerEngine).

        Offloaded to a worker thread because evaluate_cycle performs
        synchronous SQLite reads/writes that can block the event loop.
        """
        from app.core.runtime.reaction_registry import get_reaction_registry

        registry = get_reaction_registry()
        await asyncio.to_thread(registry.evaluate_cycle, kernel)

    # --- Backward compat (kept for the staleness reaction path) ----------------

    async def _process_background_tasks(self) -> None:
        """Process pending background tasks.

        Dispatch is fire-and-forget: the submit_command call (which may take
        up to 300s) runs in a background task so it never blocks the
        maintenance tick. The completion event resolves the command future
        asynchronously via _dispatch, independent of this method returning.
        """
        from app.core.runtime.agent_bootstrap import ensure_scheduler
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
                except Exception:
                    logger.exception("Background task %s failed", t_id)

            asyncio.create_task(_dispatch_bg(task_id, plan_json))


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

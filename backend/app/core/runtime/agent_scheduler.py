"""Lane A Scheduler — runs handlers as ScheduledExecution units.

Distinct from cron_registry: this module is the state machine that drives
each ScheduledExecution (pending → running → completed), persisted in
handler_executions for crash recovery.

    Event → fan-out handlers → enqueue(ScheduledExecution) → Handler

One event may produce N ScheduledExecutions (one per registered handler).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.runtime.execution_events import (
    emit_execution_completed,
    emit_execution_failed,
    emit_execution_requested,
    emit_execution_retried,
    emit_execution_started,
)

# ── Shadow-compare helpers ──

_SHADOW_FIELDS: tuple[str, ...] = (
    "id", "status", "retry_count", "created_at", "started_at", "completed_at",
    "error", "policy_json", "event_seq", "event_id", "handler_name",
    "instance_id", "correlation_id",
)


def _shadow_compare(kernel, item) -> list[str]:
    """Verify ScheduledExecution.to_row() matches handler_executions projection.

    Opt-in via ``settings.execution_shadow_compare`` (off in production).
    """
    from app.config import settings

    if not settings.execution_shadow_compare:
        return []

    import json

    def _normalize(row: dict) -> dict:
        out = {k: row.get(k) for k in _SHADOW_FIELDS if k in row}
        pj = out.get("policy_json")
        if isinstance(pj, str) and pj:
            out["policy_json"] = json.dumps(json.loads(pj), sort_keys=True)
        for key in ("started_at", "completed_at", "error"):
            if out.get(key) is None:
                out[key] = ""
        return out

    persist = item.to_row()
    # Boundary: use Kernel ABI (O(1) by id), never SELECT handler_executions here.
    projected = kernel.read_scheduled_execution(item.id)
    if projected is None:
        diffs = ["handler_executions row missing after dual-write"]
    else:
        exp = _normalize(persist)
        act = _normalize(projected.to_row())
        diffs = [
            f"{k}: persist={exp.get(k)!r} projection={act.get(k)!r}"
            for k in _SHADOW_FIELDS if exp.get(k) != act.get(k)
        ]
    if diffs:
        logger.warning("shadow compare mismatch for %s: %s", item.id, "; ".join(diffs))
    return diffs


if TYPE_CHECKING:
    from .kernel.event import Event
    from .kernel.kernel import Kernel
    from .scheduled_execution import ScheduledExecution

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 8  # max ScheduledExecutions processed per tick

# Neutral runtime identity (not an Agent concept).
_RUNTIME_INSTANCE_ID = "runtime:primary"


class Scheduler:
    """Lane A execution engine for ScheduledExecution units.

    enqueue(event) creates one ScheduledExecution per registered handler
    and enqueues them. The loop picks up pending items, executes handlers
    with timeout, and transitions status.
    """

    def __init__(self, kernel: "Kernel"):
        self._kernel = kernel
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._pending: list["ScheduledExecution"] = []
        self._tick_interval: float = 0.05

        self._recover()

    def _recover(self) -> None:
        """Recover ScheduledExecutions interrupted by a restart."""
        try:
            running, pending = self._kernel.recover_scheduled_executions()
        except Exception:
            return  # Table may not exist on first boot

        recovered = 0
        for item in running:
            item.error = "interrupted"
            item.transition_to("retrying")
            self._emit_verify(
                item,
                lambda it=item: emit_execution_retried(
                    self._kernel, it,
                    reason="interrupted",
                    status="retrying",
                ),
            )
            item.transition_to("pending")
            self._emit_verify(
                item,
                lambda it=item: emit_execution_retried(
                    self._kernel, it,
                    reason="interrupted",
                    status="pending",
                ),
            )
            self._pending.append(item)
            recovered += 1

        self._pending.extend(pending)
        recovered += len(pending)
        if recovered:
            logger.info("Scheduler: recovered %d scheduled execution(s)", recovered)

    # --- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        # Reuse the existing worker task only if it's alive on the *current*
        # event loop.  When the scheduler is restarted after the previous
        # event loop was shut down (e.g. between TestClient requests or
        # across tests), the old _worker_task is a zombie tied to a dead
        # loop — create_task() would raise.  Check both .done() and
        # .get_loop().is_closed() to detect a dead worker and recreate it.
        # The loop check closes ARCHITECTURE_SURVIVAL_REVIEW High #6: a
        # zombie task reported .done()==False on a closed loop, causing
        # start() to short-circuit and submit_command to time out (504).
        if self._worker_task is not None:
            try:
                loop_closed = self._worker_task.get_loop().is_closed()
            except RuntimeError:
                loop_closed = True
            if not self._worker_task.done() and not loop_closed:
                return
        self._running = True
        self._worker_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started (max_concurrent=%d)", _MAX_CONCURRENT)

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            try:
                self._worker_task.cancel()
            except RuntimeError:
                pass  # Event loop already closed
            try:
                await self._worker_task
            except (asyncio.CancelledError, RuntimeError):
                pass
            self._worker_task = None
        logger.info("Scheduler stopped")

    def _emit_verify(self, item: "ScheduledExecution", emit_fn) -> None:
        """Emit execution event then verify projection matches."""
        emit_fn()
        _shadow_compare(self._kernel, item)

    # --- enqueue ---------------------------------------------------------

    def enqueue(
        self,
        instance_id: str,
        actor: str,
        event: "Event",
        *,
        policy=None,
    ) -> list["ScheduledExecution"]:
        """Create one ScheduledExecution per registered handler (fan-out)."""
        from .handler_registry import get_handlers
        from .scheduled_execution import ScheduledExecution, policy_for_event

        handlers = get_handlers(event.type)
        if not handlers:
            return []

        items: list[ScheduledExecution] = []
        for handler in handlers:
            item = ScheduledExecution(
                event_seq=int(event.seq) if event.seq else 0,
                event_id=event.id,
                event_type=event.type,
                handler_name=handler.__name__,
                instance_id=instance_id,
                correlation_id=event.correlation_id or "",
                policy=policy if policy is not None else policy_for_event(event.type),
                _event=event,
            )
            self._pending.append(item)
            self._emit_verify(
                item,
                lambda it=item: emit_execution_requested(self._kernel, it, actor),
            )
            logger.debug(
                "Scheduler: enqueued %s → %s (seq=%s)",
                event.type, handler.__name__, item.event_seq,
            )
            items.append(item)
        return items

    # --- scheduling loop -------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Main scheduling loop — process pending ScheduledExecutions."""
        while self._running:
            try:
                batch = self._pending[:_MAX_CONCURRENT]
                self._pending = self._pending[_MAX_CONCURRENT:]

                if batch:
                    tasks = [self._process_work_item(item) for item in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(self._tick_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Scheduler loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def _process_work_item(self, item: "ScheduledExecution") -> None:
        """Process one ScheduledExecution through its state machine."""
        item.transition_to("running")
        self._emit_verify(
            item,
            lambda: emit_execution_started(self._kernel, item),
        )

        try:
            event = getattr(item, '_event', None)
            if event is None and item.event_id:
                # Recovery: _event lost on deserialization. Rehydrate from event_log.
                rehydrated = self._kernel.read_events(id=item.event_id, limit=1)
                if rehydrated:
                    event = rehydrated[0]
            if event is None:
                item.error = "No event attached to ScheduledExecution"
                item.transition_to("failed")
                self._emit_verify(
                    item,
                    lambda: emit_execution_failed(self._kernel, item, terminal=True),
                )
                return

            await asyncio.wait_for(
                self._execute_handler(item, event),
                timeout=item.policy.timeout_seconds,
            )
            if item.status == "failed":
                return
            item.error = None
            item.transition_to("completed")
            self._emit_verify(
                item,
                lambda: emit_execution_completed(self._kernel, item),
            )
        except asyncio.TimeoutError:
            item.error = f"Timeout after {item.policy.timeout_seconds}s"
            await self._maybe_retry(item)
        except Exception as exc:
            item.error = str(exc)
            await self._maybe_retry(item)

    async def _execute_handler(self, item: "ScheduledExecution", event: "Event") -> None:
        """Resolve the named handler for this ScheduledExecution and run it."""
        from .execution import ExecutionContext
        from .handler_registry import get_handler_named

        handler = get_handler_named(item.event_type, item.handler_name)
        if handler is None:
            item.error = f"No handler {item.handler_name!r} for {item.event_type}"
            item.transition_to("failed")
            self._emit_verify(
                item,
                lambda: emit_execution_failed(self._kernel, item, terminal=True),
            )
            return

        from .execution import identity_resolver

        actor = (
            item.instance_id
            if ":" in item.instance_id
            else f"runtime:{item.instance_id}"
        )
        principal = identity_resolver.resolve(actor, self._kernel)
        ctx = ExecutionContext(
            instance_id=item.instance_id,
            actor=actor,
            correlation_id=item.correlation_id,
            _kernel=self._kernel,
            principal=principal,
            execution_id=item.id,
        )

        from .execution import execution_scope

        with execution_scope(item.id):
            await handler(ctx, event)

    async def _maybe_retry(self, item: "ScheduledExecution") -> None:
        """Retry if within limits, else mark failed."""
        if item.can_retry():
            item.retry_count += 1
            item.transition_to("retrying")
            self._emit_verify(
                item,
                lambda: emit_execution_retried(
                    self._kernel, item, reason=item.error or "", status="retrying",
                ),
            )
            # Re-enqueue after delay
            await asyncio.sleep(item.policy.retry_delay_seconds)
            item.transition_to("pending")
            self._emit_verify(
                item,
                lambda: emit_execution_retried(
                    self._kernel, item, reason=item.error or "", status="pending",
                ),
            )
            self._pending.append(item)
            logger.info(
                "Scheduler: retrying %s (attempt %d/%d)",
                item.handler_name, item.retry_count, item.policy.max_retries,
            )
        else:
            item.transition_to("failed")
            self._emit_verify(
                item,
                lambda: emit_execution_failed(self._kernel, item, terminal=True),
            )
            logger.warning(
                "Scheduler: %s failed after %d retries: %s",
                item.handler_name, item.policy.max_retries, item.error,
            )

    # --- visibility ------------------------------------------------------

    def pending_count(self) -> int:
        return len(self._pending)

    async def flush(self) -> None:
        """Process ALL pending ScheduledExecutions immediately. For test use only."""
        while self._pending:
            items = self._pending[:]
            self._pending = []
            tasks = [self._process_work_item(item) for item in items]
            await asyncio.gather(*tasks, return_exceptions=True)

    def status_counts(self) -> dict[str, int]:
        """Return a snapshot of ScheduledExecution status distribution."""
        try:
            return self._kernel.count_scheduled_executions_by_status()
        except Exception:
            logger.exception("Scheduler: failed to read scheduled execution counts")
            raise


def get_scheduler(kernel: "Kernel") -> Scheduler:
    """Return the container-owned Scheduler (created with ``kernel`` if needed)."""
    from app.core.runtime.runtime_container import runtime

    return runtime.scheduler_for(kernel)


def reset_scheduler() -> None:
    """Reset the scheduler singleton. For test use only."""
    from app.core.runtime.runtime_container import runtime

    runtime._scheduler = None


# ── Agent bootstrap (folded from agent_bootstrap.py) ─────────────────────
# agents.handlers also pulls in runtime.handlers (capability orchestration).
import app.core.agents.handlers  # noqa: E402,F401 — registers @subscribe handlers

_started = False


async def ensure_scheduler(kernel) -> None:
    """Ensure the Scheduler is running and the event dispatcher is registered.

    Routes emitted events to Lane A (ScheduledExecution fan-out).
    """
    global _started
    if _started:
        return

    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import get_handlers

    sch = get_scheduler(kernel)
    await sch.start()

    async def _dispatch_to_scheduler(event):
        if not get_handlers(event.type):
            return
        sch.enqueue(_RUNTIME_INSTANCE_ID, _RUNTIME_INSTANCE_ID, event)

    kernel.set_async_dispatcher(_dispatch_to_scheduler)
    _started = True


def reset_agent_bootstrap() -> None:
    """Clear the ``_started`` flag so the next ``ensure_scheduler`` re-binds.

    Pairs with ``reset_scheduler`` in ``runtime_container.reset()``. Without
    this, the module-level ``_started`` boolean survives across tests: the
    fresh Kernel has no ``_async_dispatcher`` registered, but
    ``ensure_scheduler`` short-circuits and the Scheduler loop is never
    (re)started on the new event loop. This was the root cause of the
    intermittent 504s in ``test_approval_resolve`` (ARCHITECTURE_SURVIVAL_REVIEW
    High #6).
    """
    global _started
    _started = False

"""WorkItem execution engine — runs handlers within Execution context.

Distinct from scheduler.py (cron registration): this module is the
state machine that drives each WorkItem (pending → running → completed),
persisted in handler_executions for crash recovery.

    Event → AgentInstance.dispatch()
                            ↓
                      enqueue(WorkItem)
                            ↓
                      _process_work_item()
                            ↓
                      _execute_handler()
                            ↓
                      handler(instance, event)

The scheduling unit is the WorkItem, not the Agent. Every WorkItem is
persisted in handler_executions so interrupted items can be recovered
after restart.

State Machine:
    pending → running → completed
    pending → running → failed → retrying → running → completed
    retrying → failed (max retries exceeded)
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

# ── Shadow-compare helpers (inlined from execution_shadow_compare.py, v0.7.0) ──

_SHADOW_FIELDS: tuple[str, ...] = (
    "id", "status", "retry_count", "created_at", "started_at", "completed_at",
    "error", "policy_json", "event_seq", "event_id", "handler_name",
    "instance_id", "correlation_id",
)


def _shadow_compare(kernel, item) -> list[str]:
    """Verify WorkItem.to_row() matches what the projector wrote to handler_executions."""
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
    with kernel._db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM handler_executions WHERE id = ?", (item.id,),
        ).fetchone()
    if row is None:
        diffs = ["handler_executions row missing after dual-write"]
    else:
        exp = _normalize(persist)
        act = _normalize(dict(row))
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
    from .work_item import WorkItem

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 8  # max WorkItems processed per tick


class Scheduler:
    """WorkItem execution engine.

    enqueue(event, instance) creates a WorkItem from an event and enqueues
    it for processing.  The scheduler loop picks up pending items, executes
    their handlers with a timeout, and transitions their status.
    """

    def __init__(self, kernel: "Kernel"):
        self._kernel = kernel
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._pending: list["WorkItem"] = []
        self._tick_interval: float = 0.05

        # Recover interrupted WorkItems from the persistence layer
        self._recover()

    def _recover(self) -> None:
        """Recover WorkItems that were interrupted by a restart.

    ADR-0007 Step 4: the projector is the sole writer to handler_executions.
    persist_work_item is no longer called on the scheduler hot path. The
    projection IS the truth, verified after every emit by shadow compare.
        """
        try:
            running, pending = self._kernel.recover_work_items()
        except Exception:
            return  # Table may not exist on first boot

        recovered = 0
        for item in running:
            # running → retrying via event, not bare SQL UPDATE. Set item.error
            # so persist_work_item's to_row() matches the ExecutionRetried
            # projector (which writes `reason` into the `error` column), same
            # convention as the normal retry path where item.error is the
            # failure message.
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
            # Re-enqueue: retry path expects a pending→running transition
            # on the next tick, mirroring the normal retry flow.
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
            logger.info("Scheduler: recovered %d work item(s)", recovered)

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

    def _emit_verify(self, item: "WorkItem", emit_fn) -> None:
        """Emit execution event then verify projection matches (ADR-0007 Step 4).

        The projector (triggered inside emit_event) is now the SOLE writer to
        handler_executions. persist_work_item is no longer called on the hot
        path — the projection IS the truth. The verify step remains as a
        projector-correctness check: it compares the WorkItem's expected
        state against what the projector actually wrote, catching any drift
        between the event payload semantics and the projector's SQL.
        """
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
    ) -> "WorkItem":
        """Create a WorkItem from an event and enqueue it.

        ADR-0007 Step 7: takes identity primitives (instance_id, actor)
        instead of an AgentInstance object. The Scheduler no longer depends
        on AgentInstance for handler execution — it operates purely on
        execution identity derived from the event stream.
        """
        from .handler_registry import get_handler
        from .work_item import WorkItem, policy_for_event

        handler = get_handler(event.type)
        if handler is None:
            return None  # type: ignore[return-value]

        item = WorkItem(
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
            lambda: emit_execution_requested(self._kernel, item, actor),
        )
        logger.debug(
            "Scheduler: enqueued %s → %s (seq=%s)",
            event.type, handler.__name__, item.event_seq,
        )
        return item

    # --- scheduling loop -------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Main scheduling loop — process pending WorkItems.

        Each tick, take up to _MAX_CONCURRENT pending items and process
        them in order.  Items that fail and can be retried are re-enqueued.
        """
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

    async def _process_work_item(self, item: "WorkItem") -> None:
        """Process one WorkItem through its state machine."""
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
                item.error = "No event attached to WorkItem"
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

    async def _execute_handler(self, item: "WorkItem", event: "Event") -> None:
        """Look up the handler and execute it."""
        from .execution import ExecutionContext
        from .handler_registry import get_handler

        handler = get_handler(item.event_type)
        if handler is None:
            item.error = f"No handler for {item.event_type}"
            item.transition_to("failed")
            self._emit_verify(
                item,
                lambda: emit_execution_failed(self._kernel, item, terminal=True),
            )
            return

        # Construct ExecutionContext from WorkItem identity fields. This
        # decouples handler execution from AgentInstance — the handler
        # receives only what it needs (identity + emit + Principal), not
        # the full AgentInstance object. (ADR-0007 Step 5 + Step 8)
        from .execution import identity_resolver

        actor = f"agent:{item.instance_id}"
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

    async def _maybe_retry(self, item: "WorkItem") -> None:
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
        """Process ALL pending WorkItems immediately. For test use only."""
        while self._pending:
            items = self._pending[:]
            self._pending = []
            tasks = [self._process_work_item(item) for item in items]
            await asyncio.gather(*tasks, return_exceptions=True)

    def status_counts(self) -> dict[str, int]:
        """Return a snapshot of WorkItem status distribution."""
        counts: dict[str, int] = {}
        try:
            items = self._kernel.read_work_items()
            for item in items:
                counts[item.status] = counts.get(item.status, 0) + 1
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Scheduler: failed to read work item counts", exc_info=True
            )
        return counts


# Global singleton
_scheduler: Scheduler | None = None


def get_scheduler(kernel: "Kernel") -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(kernel)
    return _scheduler


def reset_scheduler() -> None:
    """Reset the scheduler singleton. For test use only."""
    global _scheduler
    _scheduler = None


# ── Agent bootstrap (folded from agent_bootstrap.py) ─────────────────────
import app.core.agents.handlers  # noqa: E402,F401 — registers @subscribe handlers

_started = False


async def ensure_scheduler(kernel) -> None:
    """Ensure the Scheduler is running and the event dispatcher is registered.

    Registers a kernel-level dispatcher that routes all emitted events to the
    Scheduler's WorkItem engine. Handler matching is done by handler_registry.
    """
    global _started
    if _started:
        return

    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.handler_registry import get_handler

    sch = get_scheduler(kernel)
    await sch.start()

    _AGENT_ID = "agent:primary"

    async def _dispatch_to_scheduler(event):
        handler = get_handler(event.type)
        if handler is None:
            return
        sch.enqueue(_AGENT_ID, _AGENT_ID, event)

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

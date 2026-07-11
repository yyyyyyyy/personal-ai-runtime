"""The Kernel — the boundary of the Personal AI Runtime.

This is Kernel Space. It alone touches storage. Everything in User Space
(agents, workflows, APIs, UI) must go through this ABI and may never read or
write the database directly.

This module implements the core P0 ABI from docs/RUNTIME_SPEC.md §3.1:
    emit_event / read_events / subscribe_events / query_state

Governance (approval workflows) → kernel_governance.py (GovernanceMixin)
Query state (read projections) → kernel_query_state.py (QueryStateMixin)
Sovereignty (export/import/rebuild) → kernel_sovereignty.py (SovereigntyMixin)
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Callable

from . import projectors
from .constants import (
    MEMORY_INDEX_EVENT_TYPES,
)
from .event import Event
from .kernel_governance import GovernanceMixin
from .kernel_query_state import QueryStateMixin
from .kernel_sovereignty import SovereigntyMixin
from .query_builder import build_where, safe_limit, safe_offset, safe_order

if TYPE_CHECKING:
    import asyncio

logger = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]


def _log_dispatch_task_exception(task: "asyncio.Task") -> None:
    """Done callback for fire-and-forget Event dispatch tasks.

    Without this, exceptions inside async dispatchers live only in the
    task's _exception attribute and are never logged — making production
    debugging nearly impossible.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Event dispatch task failed: %s",
            exc,
            exc_info=exc,
        )


# In-process queue of memory events whose Chroma index sync failed.
# Kept as an in-memory mirror of the durable `memory_index_repairs` table for
# cheap runtime observability. The authoritative repair queue lives in
# SQLite and is drained by RuntimeLoop._maintenance; this deque only holds
# the most recent failures (maxlen) so dashboards can surface them without
# hitting the DB.
_MAX_PENDING_MEMORY_INDEX_REPAIRS = 1000
_pending_memory_index_repairs: deque[dict[str, object]] = deque(
    maxlen=_MAX_PENDING_MEMORY_INDEX_REPAIRS
)


def get_pending_memory_index_repairs() -> list[dict[str, object]]:
    """Return a snapshot of memory index events awaiting Chroma reconciliation."""
    return list(_pending_memory_index_repairs)


def clear_pending_memory_index_repairs() -> int:
    """Clear the in-process repair queue; returns number of entries removed.

    NOTE: this only clears the in-memory mirror. The durable rows in
    ``memory_index_repairs`` survive process restarts and are drained by the
    RuntimeLoop repair worker. Tests that need a clean slate should also
    truncate the table.
    """
    count = len(_pending_memory_index_repairs)
    _pending_memory_index_repairs.clear()
    return count


def _persist_memory_index_repair(
    db,
    aggregate_id: str,
    event_type: str,
    event_seq: int,
    error: str,
) -> None:
    """Append a failed memory index sync to the durable repair queue.

    Idempotent on (aggregate_id, event_seq): if a row already exists for the
    same event we leave it untouched so the retry counter and status reflect
    the original failure rather than being reset on every emit.
    """
    from datetime import UTC, datetime

    now_iso = datetime.now(UTC).isoformat()
    try:
        with db.get_db() as conn:
            existing = conn.execute(
                "SELECT 1 FROM memory_index_repairs "
                "WHERE aggregate_id = ? AND event_seq = ? LIMIT 1",
                (aggregate_id, event_seq),
            ).fetchone()
            if existing:
                return
            conn.execute(
                "INSERT INTO memory_index_repairs "
                "(aggregate_id, event_type, event_seq, error, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (aggregate_id, event_type, event_seq, error[:500], now_iso),
            )
    except Exception:
        # If the table does not exist yet (pre-migration) we cannot persist;
        # fall back to in-memory only so emit_event is not blocked.
        logger.debug(
            "Could not persist memory index repair for %s — table unavailable",
            aggregate_id,
            exc_info=True,
        )

class Kernel(QueryStateMixin, GovernanceMixin, SovereigntyMixin):
    def __init__(self, db=None, *, memory_index=None):
        # Default to the global Database singleton; tests inject their own.
        if db is None:
            from app.store.database import db as global_db

            db = global_db
        self._db = db
        self._memory_index = memory_index  # MemoryIndexPort | None
        self._subscribers: list[tuple[dict, Subscriber]] = []
        self._async_dispatcher: Callable | None = None
        self._pending_commands: dict[tuple[str, str], "asyncio.Future"] = {}
        self._commands_lock = threading.Lock()
        self._ensure_schema()

    # -- Task & Agent lifecycle -----------------------------------------------

    def _ensure_schema(self) -> None:
        """Run Alembic migrations; fall back to raw DDL for test/custom DBs."""
        from app.store.schema_init import ensure_schema
        ensure_schema(self._db)

    # --- Truth layer ---------------------------------------------------------

    def emit_event(
        self,
        type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object] | None = None,
        actor: str = "system",
        caused_by: str | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        """Append an immutable event, project it to State, then notify subscribers.

        This is the ONLY write entry point into the Runtime. Every state change
        in the system flows through here, which is what makes the Event Log the
        authoritative truth.
        """
        event = Event(
            type=type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            actor=actor,
            caused_by=caused_by,
            correlation_id=correlation_id,
        )

        # NOTE: Vector index sync happens post-commit in _sync_memory_index.
        # Previously embedding was pre-computed here so the projector could
        # write embedding_id in the same transaction. However that created an
        # asymmetric failure mode: if embedding succeeded but the SQLite INSERT
        # failed (transaction rollback), ChromaDB was left with an orphan vector.
        # The post-commit path is eventually-consistent (embedding_id starts
        # NULL, backfilled via MemoryUpdated or the durable repair queue) but
        # never produces orphans because the event is already durable before
        # ChromaDB is touched.

        with self._db.get_db() as conn:
            cur = conn.execute(
                """INSERT INTO event_log
                   (id, type, aggregate_type, aggregate_id, actor, payload,
                    caused_by, correlation_id, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.type,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.actor,
                    json.dumps(event.payload),
                    event.caused_by,
                    event.correlation_id,
                    event.ts,
                ),
            )
            seq = int(cur.lastrowid)
            # Project synchronously in the same transaction so State stays
            # consistent with the Event that produced it.
            event = event.with_seq(seq)
            projectors.apply(event, conn)

        self._sync_memory_index(event)
        self._dispatch(event)
        self._notify_goal_changed(event)
        return event

    async def submit_command(
        self,
        type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object] | None = None,
        actor: str = "system",
        caused_by: str | None = None,
        correlation_id: str | None = None,
        *,
        timeout: float = 60.0,
        completion_type: str | None = None,
    ) -> dict:
        """Emit an event and wait for a completion event synchronously.

        This is NOT a new Ontology layer. It is a synchronous wrapper around
        emit_event — analogous to Linux read() operating on File without
        read being a new Primitive.

        Uses correlation_id to match the completion event. Internally
        registers an asyncio.Future keyed by (correlation_id, completion_type)
        and resolves it when _dispatch sees a matching event.

        Returns the completion event's payload dict, or {"error": "timeout"}.
        """
        import asyncio

        if correlation_id is None:
            import uuid
            correlation_id = f"cmd_{uuid.uuid4().hex[:12]}"

        if completion_type is None:
            # Default: same event type with "Completed" suffix
            # e.g. "ExecuteRequested" → "ExecuteCompleted"
            if type.endswith("Requested"):
                completion_type = type.replace("Requested", "Completed")
            else:
                completion_type = type + "Completed"

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        key = (correlation_id, completion_type)
        with self._commands_lock:
            self._pending_commands[key] = future

        try:
            self.emit_event(
                type=type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload or {},
                actor=actor,
                caused_by=caused_by,
                correlation_id=correlation_id,
            )

            result = await asyncio.wait_for(future, timeout=timeout)
            return result.payload
        except asyncio.TimeoutError:
            return {"error": "timeout", "status": "timeout"}
        except Exception as exc:
            return {"error": str(exc), "status": "error"}
        finally:
            # Defensive cleanup: guarantee the registration never leaks even
            # if _dispatch misses the completion event (e.g. no running loop,
            # handler raised before resolving, process fork). This is the
            # single source of truth for key removal — _dispatch also pops
            # on successful resolve, but pop(key, None) here is a safe no-op
            # in that case.
            with self._commands_lock:
                self._pending_commands.pop(key, None)

    def _sync_memory_index(self, event: Event) -> None:
        """Synchronise memory events with the MemoryIndexPort (if configured).

        Post-commit vector index sync. Called after emit_event has durably
        written the event + projection in a single SQLite transaction.
        Because the event is already durable, a ChromaDB failure here can
        never orphan an event — it only leaves embedding_id NULL until the
        repair queue retries.
        """
        if event.type not in MEMORY_INDEX_EVENT_TYPES:
            return
        content = str(event.payload.get("content", ""))
        try:
            if self._memory_index is not None:
                if event.type == "MemoryDeleted":
                    self._memory_index.delete_memory(event.aggregate_id)
                elif not event.payload.get("embedding_id") and content:
                    embedding_id = self._memory_index.index_memory(
                        content=content,
                        metadata={
                            "category": str(event.payload.get("category", "general")),
                            "source": str(event.payload.get("source", "")),
                        },
                        memory_id=event.aggregate_id,
                    )
                    try:
                        self.emit_event(
                            "MemoryUpdated", "memory", event.aggregate_id,
                            payload={"embedding_id": embedding_id},
                            actor="kernel",
                        )
                    except Exception:
                        logger.debug("Backfill embedding_id failed for %s", event.aggregate_id, exc_info=True)
        except Exception as exc:
            # Compensating delete: if index_memory failed partway, attempt to
            # remove any partial ChromaDB state so the repair retry starts clean.
            if event.type != "MemoryDeleted" and self._memory_index is not None:
                try:
                    self._memory_index.delete_memory(event.aggregate_id)
                except Exception:
                    logger.debug("Compensating delete failed for %s", event.aggregate_id, exc_info=True)
            _pending_memory_index_repairs.append({
                "aggregate_id": event.aggregate_id,
                "event_type": event.type,
                "seq": event.seq,
                "error": str(exc),
            })
            _persist_memory_index_repair(
                self._db, event.aggregate_id, event.type,
                event.seq or 0, str(exc),
            )
            logger.warning(
                "Memory index sync failed for %s (%s) — queued for repair "
                "(in-memory mirror: %d entries). The durable row will be "
                "drained by RuntimeLoop; check 'memory_index_repairs' table "
                "if recovery does not happen.",
                event.aggregate_id, event.type, len(_pending_memory_index_repairs),
                exc_info=True,
            )
        self._notify_memory_changed(event, content if content else "")

    def _notify_memory_changed(self, event: Event, content: str) -> None:
        """Push a lightweight WS event so frontends can invalidate caches.

        Pure transport — does NOT persist a notification row (the
        MemoryDerived/Updated event is the authoritative record). Failures
        here must never affect storage; they are swallowed at DEBUG level
        inside ``broadcast_event``.
        """
        from app.core.runtime.notification_bridge import broadcast_event

        broadcast_event({
            "type": "memory_changed",
            "event_type": event.type,
            "memory_id": event.aggregate_id,
            "category": event.payload.get("category", "general"),
            "preview": (content or "")[:120],
            "ts": event.ts,
        })

    _GOAL_NOTIFY_TYPES = frozenset({
        "WorkItemCreated",
        "WorkItemUpdated",
        "WorkItemStatusChanged",
        "WorkItemDeleted",
    })

    def _notify_goal_changed(self, event: Event) -> None:
        """Push a WS hint when work_items (goals/actions) change."""
        if event.type not in self._GOAL_NOTIFY_TYPES:
            return
        if event.aggregate_type != "work_item":
            return
        from app.core.runtime.notification_bridge import broadcast_event

        broadcast_event({
            "type": "goal_changed",
            "event_type": event.type,
            "work_item_id": event.aggregate_id,
            "work_type": event.payload.get("work_type"),
            "ts": event.ts,
        })

    def read_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        type: str | None = None,
        types: list[str] | None = None,
        correlation_id: str | None = None,
        since_seq: int = 0,
        since_ts: str | None = None,
        until_ts: str | None = None,
        payload_goal_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order: str = "asc",
        id: str | None = None,
    ) -> list[Event]:
        """Read the log (pull). Foundation for replay, projection, audit."""
        clauses = ["seq > ?"]
        params: list[Any] = [since_seq]
        if id is not None:
            clauses.append("id = ?")
            params.append(id)
        if aggregate_type is not None:
            clauses.append("aggregate_type = ?")
            params.append(aggregate_type)
        if aggregate_id is not None:
            clauses.append("aggregate_id = ?")
            params.append(aggregate_id)
        if types:
            placeholders = ",".join("?" * len(types))
            clauses.append(f"type IN ({placeholders})")
            params.extend(types)
        elif type is not None:
            clauses.append("type = ?")
            params.append(type)
        if payload_goal_id is not None:
            clauses.append(
                "(json_extract(payload, '$.goal_id') = ? OR "
                "json_extract(payload, '$.parent_goal_id') = ?)"
            )
            params.append(payload_goal_id)
            params.append(payload_goal_id)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if since_ts is not None:
            clauses.append("ts >= ?")
            params.append(since_ts)
        if until_ts is not None:
            clauses.append("ts <= ?")
            params.append(until_ts)
        where = build_where(clauses)
        order_sql = safe_order(
            order,
            {"asc": "seq ASC", "desc": "seq DESC"},
            default_key="asc",
        )
        limit_sql = safe_limit(limit)
        offset_sql = safe_offset(offset)
        with self._db.get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log{where}{order_sql}{limit_sql}{offset_sql}",
                params,
            ).fetchall()
        return [Event.from_row(r) for r in rows]

    def read_events_by_seqs(self, seqs: list[int]) -> list[Event]:
        """Fetch events by global log sequence (kernel-space batch read)."""
        if not seqs:
            return []
        unique = sorted({int(s) for s in seqs})
        placeholders = ",".join("?" * len(unique))
        with self._db.get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log WHERE seq IN ({placeholders}) ORDER BY seq ASC",
                unique,
            ).fetchall()
        return [Event.from_row(r) for r in rows]

    def subscribe_events(
        self,
        handler: Subscriber,
        type: str | None = None,
        aggregate_type: str | None = None,
    ) -> Callable[[], None]:
        """Subscribe to the event stream (push). This is what turns the Event Log
        from a mere log into a Runtime Event Bus. Returns an unsubscribe callable."""
        flt = {"type": type, "aggregate_type": aggregate_type}
        entry = (flt, handler)
        self._subscribers.append(entry)

        def unsubscribe() -> None:
            if entry in self._subscribers:
                self._subscribers.remove(entry)

        return unsubscribe

    def set_async_dispatcher(self, dispatcher: Callable) -> None:
        """Set the async dispatcher that will be fire-and-forget called on
        every event emitted by this kernel.

        Replaces the old multi-dispatcher list — only one consumer ever
        registers (the Scheduler via ``agent_bootstrap.ensure_scheduler``).
        Calling again overwrites the previous dispatcher (set semantics).

        This replaces the old AgentBus mechanism: the persistent scheduler
        registers its dispatch handler here, and _dispatch() fires it for
        every event so the Scheduler can route events to registered
        @subscribe handlers.
        """
        self._async_dispatcher = dispatcher

    def _dispatch(self, event: Event) -> None:
        for flt, handler in list(self._subscribers):
            if flt["type"] and flt["type"] != event.type:
                continue
            if flt["aggregate_type"] and flt["aggregate_type"] != event.aggregate_type:
                continue
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "Event subscriber failed for %s (aggregate=%s/%s): %s",
                    event.type,
                    event.aggregate_type,
                    event.aggregate_id,
                    exc,
                    exc_info=True,
                )

        # Fire registered async dispatchers (persistent agent → Scheduler).
        # Storage has already committed; this dispatch is best-effort delivery.
        # If no event loop is running (sync context / tests), we log at DEBUG
        # so the gap is observable. P1 (Event Log = truth) is not violated
        # because storage has already committed the event by this point;
        # subscribers that miss the live push will see it on next read_events.
        if self._async_dispatcher is not None:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._async_dispatcher(event))
                task.add_done_callback(_log_dispatch_task_exception)
                if not hasattr(self, "_dispatch_tasks"):
                    self._dispatch_tasks: set[asyncio.Task] = set()
                task.add_done_callback(self._dispatch_tasks.discard)
                self._dispatch_tasks.add(task)
            except RuntimeError:
                # No running loop — fire-and-forget delivery is unavailable.
                # This is expected in synchronous test contexts.
                logger.debug(
                    "Event dispatch skipped (no running loop) for %s "
                    "aggregate=%s/%s — event is persisted, subscribers "
                    "will see it on next read_events/replay.",
                    event.type,
                    event.aggregate_type,
                    event.aggregate_id,
                )

        # Resolve pending submit_command Futures.
        # When a "Completed" event with matching correlation_id arrives,
        # resolve the Future so the await in submit_command returns.
        key = (event.correlation_id or "", event.type)
        with self._commands_lock:
            future = self._pending_commands.pop(key, None)
        if future is not None and not future.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — cannot schedule the resolution callback.
                # The future has already been popped above; submit_command's
                # wait_for will time out and its finally block guarantees the
                # key is gone. We deliberately do NOT cancel the future here:
                # cancelling would inject a CancelledError into wait_for,
                # which asyncio then propagates as a task cancellation — hard
                # to distinguish from a genuine caller cancellation. Letting
                # it time out is safer and the timeout is already bounded.
                return
            # Use a nested function instead of lambda for mypy type inference
            def _resolve_pending(f: "asyncio.Future", e: Event) -> None:
                if not f.done():
                    f.set_result(e)
            loop.call_soon_threadsafe(_resolve_pending, future, event)

        # Background tasks: Failed also resolves Requested → Completed waiters.
        if event.type == "BackgroundTaskFailed" and event.correlation_id:
            fail_key = (event.correlation_id, "BackgroundTaskCompleted")
            with self._commands_lock:
                fail_future = self._pending_commands.pop(fail_key, None)
            if fail_future is not None and not fail_future.done():
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # Same reasoning as above: let it time out rather than
                    # injecting a CancelledError.
                    return

                def _resolve_failed(f: "asyncio.Future", e: Event) -> None:
                    if not f.done():
                        f.set_result(e)

                loop.call_soon_threadsafe(_resolve_failed, fail_future, event)

    # --- Read layer (projections) -------------------------------------------
    # See kernel_query_state.py (QueryStateMixin) for:
    #   query_state() / list_capability_definitions() / recall_memory()

    # --- Governance layer ----------------------------------------------------

    # See kernel_governance.py for:
    #   request_approval() / grant_approval() / deny_approval()
    #   invoke_capability() / _handler_execution_exists()

    # --- WorkItem persistence (Execution Model) ---------------------------
    # Read paths live in work_item_repository.py (still Kernel Space).
    # Writes are performed exclusively by the execution projectors reacting
    # to Execution* events — these methods only scan the projection.

    def read_work_items(
        self,
        status: str | None = None,
        instance_id: str | None = None,
    ) -> list:
        """Read WorkItems from handler_executions for recovery.

        Used by Scheduler to find pending/running items after restart.
        """
        from . import work_item_repository
        return work_item_repository.read_work_items(self._db, status, instance_id)

    def recover_work_items(self) -> tuple[list, list]:
        """Scan WorkItems in 'pending' or 'retrying' state for re-enqueue.

        ADR-0007 Step 3: this method is now a pure scanner — it performs
        NO writes to handler_executions. Interrupted ('running') items are
        NOT mutated here; the caller (Scheduler._recover) drives the
        running → retrying transition by emitting ExecutionRetried events
        through the normal _persist_emit_verify path, so that every recovery
        state change is attributable to an event in event_log.

        Returns (running_items, pending_items) where running_items still
        have status='running' in the projection and MUST be transitioned by
        the caller before being re-enqueued.
        """
        from . import work_item_repository
        return work_item_repository.recover_work_items(self._db)

    # --- Data sovereignty (export / import / rebuild) -----------------------

    # See kernel_sovereignty.py for:
    #   export_event_log_rows() / import_event_log_rows() / table_counts()
    #   bootstrap_chat_from_snapshot() / export_chat_rows()
    #   rebuild() / rebuild_all()
    #   save_projection_snapshot() / save_projection_snapshots()
    #   _drop_event_log_guards() / _ensure_event_log_guards()
    #   _restore_table_snapshot()

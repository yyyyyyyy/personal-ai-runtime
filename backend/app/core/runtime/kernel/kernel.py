"""The Kernel — the boundary of the Personal AI Runtime.

This is Kernel Space. It alone touches storage. Everything in User Space
(agents, workflows, APIs, UI) must go through this ABI and may never read or
write the database directly.

This module implements the core P0 ABI from docs/RUNTIME_SPEC.md §3.1:
    emit_event / read_events / subscribe_events / query_state

Governance → governance_ops.py (methods on Kernel)
Query state (selector router) → kernel_query_state.py; SQL → query_builder.py
Sovereignty → kernel_sovereignty.py → sovereignty_ops.py; memory sync → memory_index_sync.py
Event bus (_dispatch / submit_command) → event_dispatch.py
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any, Callable

from . import event_dispatch
from . import governance_ops as _gov_ops
from . import projectors_registry as projectors
from .event import Event
from .kernel_query_state import QueryStateMixin
from .kernel_sovereignty import SovereigntyMixin
from .memory_index_sync import (  # noqa: F401 — re-exported for tests / RuntimeContainer
    clear_pending_memory_index_repairs,
    drain_memory_index_repairs,
    get_pending_memory_index_repairs,
    sync_memory_index,
)

if TYPE_CHECKING:
    import asyncio

Subscriber = Callable[[Event], None]

DEFAULT_APPROVAL_TTL_SECONDS = _gov_ops.DEFAULT_APPROVAL_TTL_SECONDS


# Re-exported for tests / RuntimeContainer (impl in memory_index_sync).
# get_pending_memory_index_repairs / clear_pending_memory_index_repairs
# are imported above.

class Kernel(QueryStateMixin, SovereigntyMixin):
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
        event = Event.create(
            type=type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
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
        """Emit an event and wait for a completion event (see event_dispatch)."""
        return await event_dispatch.submit_command(
            self,
            type,
            aggregate_type,
            aggregate_id,
            payload=payload,
            actor=actor,
            caused_by=caused_by,
            correlation_id=correlation_id,
            timeout=timeout,
            completion_type=completion_type,
        )


    def _sync_memory_index(self, event: Event) -> None:
        """Post-commit MemoryIndexPort sync (see memory_index_sync)."""
        sync_memory_index(self, event)

    def drain_memory_index_repairs(self) -> None:
        """Retry durable memory_index_repairs rows (Kernel Space ABI)."""
        drain_memory_index_repairs(self)

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
        from .query_builder import fetch_event_log_rows

        rows = fetch_event_log_rows(
            self._db,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            type=type,
            types=types,
            correlation_id=correlation_id,
            since_seq=since_seq,
            since_ts=since_ts,
            until_ts=until_ts,
            payload_goal_id=payload_goal_id,
            limit=limit,
            offset=offset,
            order=order,
            id=id,
        )
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
        registers (the Scheduler via ``agent_scheduler.ensure_scheduler``).
        Calling again overwrites the previous dispatcher (set semantics).

        This replaces the old AgentBus mechanism: the persistent scheduler
        registers its dispatch handler here, and _dispatch() fires it for
        every event so the Scheduler can route events to registered
        @subscribe handlers.
        """
        self._async_dispatcher = dispatcher

    def _dispatch(self, event: Event) -> None:
        """Push to subscribers / async dispatcher / command Futures."""
        event_dispatch.dispatch(self, event)

    # --- Read layer (projections) -------------------------------------------
    # See kernel_query_state.py (QueryStateMixin) for:
    #   query_state() / list_capability_definitions() / recall_memory()

    # --- Governance layer ----------------------------------------------------

    # --- ScheduledExecution persistence (Lane A) ---------------------------
    # Read paths live in execution_repository.py (Kernel Space).
    # Writes are exclusively via Execution* projectors.

    def read_scheduled_execution(self, execution_id: str):
        """O(1) read of one ScheduledExecution by id (Lane A projection)."""
        from . import execution_repository
        return execution_repository.read_scheduled_execution(self._db, execution_id)

    def read_scheduled_executions(
        self,
        status: str | None = None,
        instance_id: str | None = None,
    ) -> list:
        """Read ScheduledExecutions from handler_executions (Scheduler recovery).

        Prefer ``read_scheduled_execution(id)`` for single-row lookups.
        """
        from . import execution_repository
        return execution_repository.read_scheduled_executions(
            self._db, status, instance_id,
        )

    def recover_scheduled_executions(self) -> tuple[list, list]:
        """Scan ScheduledExecutions needing recovery (pure read; no writes)."""
        from . import execution_repository
        return execution_repository.recover_scheduled_executions(self._db)

    def count_scheduled_executions_by_status(self) -> dict[str, int]:
        """Return ``{status: count}`` without loading execution rows."""
        from . import execution_repository
        return execution_repository.count_scheduled_executions_by_status(self._db)

    # --- Governance (ex-GovernanceMixin / governance_ops) --------------------

    def request_approval(self, action: str, risk: str = 'low', ctx: dict[str, Any] | None = None, actor: str = 'system', correlation_id: str | None = None, expires_in_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS) -> dict:
        """Request approval for a capability invocation."""
        return _gov_ops.request_approval(self, action, risk, ctx, actor, correlation_id, expires_in_seconds)

    def expire_stale_approvals(self) -> int:
        """Expire all pending approvals whose expires_at has passed."""
        return _gov_ops.expire_stale_approvals(self)

    def grant_approval(self, approval_id: str, action: str = '', actor: str = 'user', reason: str = '', correlation_id: str | None = None) -> None:
        """Record an approval grant on the governed approval projection."""
        return _gov_ops.grant_approval(self, approval_id, action, actor, reason, correlation_id)

    def deny_approval(self, approval_id: str, action: str = '', actor: str = 'user', reason: str = '', correlation_id: str | None = None) -> None:
        """Record an approval denial on the governed approval projection."""
        return _gov_ops.deny_approval(self, approval_id, action, actor, reason, correlation_id)

    def _notify_approval_changed(self, approval_id: str, *, status: str, action: str, event_type: str) -> None:
        """Push a lightweight WS hint so Approvals / Trust caches refresh."""
        return _gov_ops._notify_approval_changed(self, approval_id, status=status, action=action, event_type=event_type)

    def _handler_execution_exists(self, execution_id: str) -> bool:
        return _gov_ops._handler_execution_exists(self, execution_id)

    async def invoke_capability(self, name: str, args: dict[str, Any] | None = None, actor: str = 'system', correlation_id: str | None = None, caused_by: str | None = None, pre_approved: bool = False, approval_id: str | None = None, principal: Any | None = None, execution_id: str | None = None) -> dict:
        """Invoke a capability through the Kernel, with approval gating."""
        return await _gov_ops.invoke_capability(self, name, args, actor, correlation_id, caused_by, pre_approved, approval_id, principal, execution_id)

    # --- Data sovereignty (export / import / rebuild) -----------------------

    # See kernel_sovereignty.py for:
    #   export_event_log_rows() / import_event_log_rows() / table_counts()
    #   bootstrap_chat_from_snapshot() / export_chat_rows()
    #   rebuild() / rebuild_all()
    #   save_projection_snapshot() / save_projection_snapshots()
    #   _drop_event_log_guards() / _ensure_event_log_guards()
    #   _restore_table_snapshot()

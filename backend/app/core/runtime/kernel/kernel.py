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

import json
import logging
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
from .query_builder import build_where, safe_limit, safe_order

if TYPE_CHECKING:
    import asyncio

    from .agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]


def _log_agent_bus_task_exception(task: "asyncio.Task") -> None:
    """Done callback for fire-and-forget AgentBus publish tasks.

    Without this, exceptions inside agent_bus.publish() live only in the
    task's _exception attribute and are never logged — making production
    debugging nearly impossible.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "AgentBus publish task failed for event: %s",
            exc,
            exc_info=exc,
        )


# In-process queue of memory events whose Chroma index sync failed (repair hint only).
_MAX_PENDING_MEMORY_INDEX_REPAIRS = 1000
_pending_memory_index_repairs: deque[dict[str, object]] = deque(
    maxlen=_MAX_PENDING_MEMORY_INDEX_REPAIRS
)


def get_pending_memory_index_repairs() -> list[dict[str, object]]:
    """Return a snapshot of memory index events awaiting Chroma reconciliation."""
    return list(_pending_memory_index_repairs)


def clear_pending_memory_index_repairs() -> int:
    """Clear the in-process repair queue; returns number of entries removed."""
    count = len(_pending_memory_index_repairs)
    _pending_memory_index_repairs.clear()
    return count

# ── Schema DDL (fallback for custom-DB tests & pre-Alembic envs) ───────────

EVENT_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_log (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    id             TEXT NOT NULL UNIQUE,
    type           TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id   TEXT NOT NULL,
    actor          TEXT NOT NULL DEFAULT 'system',
    payload        TEXT,
    caused_by      TEXT,
    correlation_id TEXT,
    ts             DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_log_aggregate
    ON event_log (aggregate_type, aggregate_id, seq);
CREATE INDEX IF NOT EXISTS idx_event_log_correlation
    ON event_log (correlation_id);
CREATE TRIGGER IF NOT EXISTS event_log_no_update
    BEFORE UPDATE ON event_log
    BEGIN SELECT RAISE(ABORT, 'event_log is append-only: UPDATE forbidden'); END;
CREATE TRIGGER IF NOT EXISTS event_log_no_delete
    BEFORE DELETE ON event_log
    BEGIN SELECT RAISE(ABORT, 'event_log is append-only: DELETE forbidden'); END;
"""

PROJECTION_CHECKPOINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS projection_checkpoints (
    agent_id         TEXT NOT NULL DEFAULT 'kernel',
    aggregate_type   TEXT NOT NULL,
    last_applied_seq INTEGER NOT NULL,
    snapshot_json    TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (agent_id, aggregate_type)
);
"""

HANDLER_EXECUTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS handler_executions (
    id               TEXT PRIMARY KEY,
    event_seq        INTEGER NOT NULL,
    event_id         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    handler_name     TEXT NOT NULL,
    instance_id      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    retry_count      INTEGER NOT NULL DEFAULT 0,
    policy_json      TEXT NOT NULL DEFAULT '{}',
    correlation_id   TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    started_at       TEXT NOT NULL DEFAULT '',
    completed_at     TEXT NOT NULL DEFAULT '',
    error            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_handler_executions_status
    ON handler_executions (status);
CREATE INDEX IF NOT EXISTS idx_handler_executions_instance
    ON handler_executions (instance_id);
"""

MEMORIES_LEGACY_DDL = [
    "ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.5",
    "ALTER TABLE memories ADD COLUMN derived_from_event TEXT",
    "ALTER TABLE memories ADD COLUMN decayed_at DATETIME",
    "ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'",
    "ALTER TABLE memories ADD COLUMN origin TEXT DEFAULT 'claim'",
    "ALTER TABLE memories ADD COLUMN claim_status TEXT",
]


class Kernel(QueryStateMixin, GovernanceMixin, SovereigntyMixin):
    def __init__(self, db=None):
        # Default to the global Database singleton; tests inject their own.
        if db is None:
            from app.store.database import db as global_db

            db = global_db
        self._db = db
        self._subscribers: list[tuple[dict, Subscriber]] = []
        self._pending_commands: dict[tuple[str, str], "asyncio.Future"] = {}
        self._ensure_schema()

    @property
    def agent_registry(self) -> "AgentRegistry":
        """Lazy-initialized AgentRegistry for multi-agent runtime support."""
        if not hasattr(self, "_agent_registry"):
            from app.core.runtime.agent_registry import AgentRegistry
            self._agent_registry = AgentRegistry(self)
        return self._agent_registry

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
            self._pending_commands.pop(key, None)
            return {"error": "timeout", "status": "timeout"}
        except Exception as exc:
            self._pending_commands.pop(key, None)
            return {"error": str(exc), "status": "error"}

    def _sync_memory_index(self, event: Event) -> None:
        """Keep ChromaDB as a derived index of memory projection events.

        Runs after the SQL transaction commits so Chroma failures cannot roll
        back governed memory events or projections.
        """
        if event.type not in MEMORY_INDEX_EVENT_TYPES:
            return
        try:
            from app.store.vector import vector_store

            if event.type == "MemoryDeleted":
                vector_store.delete_memory(event.aggregate_id)
                # Frontends must invalidate even on delete — otherwise a
                # deleted row stays visible until next manual refresh.
                self._notify_memory_changed(event, "")
                return

            p = event.payload
            vector_store.delete_memory(event.aggregate_id)
            category = p.get("category", "general")
            content = p.get("content", "")
            embedding_id = vector_store.add_memory(
                content=content,
                metadata={"category": category, "source": p.get("source", "")},
                memory_id=event.aggregate_id,
            )
            with self._db.get_db() as conn:
                conn.execute(
                    "UPDATE memories SET embedding_id = ? WHERE id = ?",
                    (embedding_id, event.aggregate_id),
                )
            # Notify frontend subscribers that a memory projection changed,
            # so they can invalidate their cache without polling. This is a
            # pure transport event — it carries no new truth (the MemoryDerived
            # event above is the authoritative record) and never blocks on the
            # WS path failing.
            self._notify_memory_changed(event, content)
        except Exception as exc:
            repair_hint = "Run `make vector-consistency-verify` to reconcile SQLite and Chroma."
            _pending_memory_index_repairs.append(
                {
                    "aggregate_id": event.aggregate_id,
                    "event_type": event.type,
                    "seq": event.seq,
                    "error": str(exc),
                }
            )
            logger.warning(
                "Memory index sync failed for %s (%s): %s — %s "
                "(%d event(s) pending repair)",
                event.aggregate_id,
                event.type,
                exc,
                repair_hint,
                len(_pending_memory_index_repairs),
            )

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

    def read_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        type: str | None = None,
        types: list[str] | None = None,
        correlation_id: str | None = None,
        since_seq: int = 0,
        since_ts: str | None = None,
        payload_goal_id: str | None = None,
        limit: int | None = None,
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
            clauses.append("json_extract(payload, '$.goal_id') = ?")
            params.append(payload_goal_id)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if since_ts is not None:
            clauses.append("ts >= ?")
            params.append(since_ts)
        where = build_where(clauses)
        order_sql = safe_order(
            order,
            {"asc": "seq ASC", "desc": "seq DESC"},
            default_key="asc",
        )
        limit_sql = safe_limit(limit)
        with self._db.get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log{where}{order_sql}{limit_sql}",
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

        # Publish to AgentBus so AgentInstances can react (fire-and-forget).
        # Storage has already committed; this dispatch is best-effort delivery.
        # If no event loop is running (sync context / tests), we log at DEBUG
        # so the gap is observable. P1 (Event Log = truth) is not violated
        # because storage has already committed the event by this point;
        # subscribers that miss the live push will see it on next read_events.
        try:
            import asyncio

            from app.core.runtime.agent_bus import agent_bus

            loop = asyncio.get_running_loop()
            task = loop.create_task(agent_bus.publish(event))
            # Log exceptions that would otherwise be silently swallowed.
            task.add_done_callback(_log_agent_bus_task_exception)
            # Hold a strong reference to prevent "was never awaited" warnings
            # when the event loop shuts down before the task completes.
            if not hasattr(self, "_agent_bus_tasks"):
                self._agent_bus_tasks: set[asyncio.Task] = set()
            # Use done callback for O(1) cleanup instead of filtering on every dispatch
            task.add_done_callback(self._agent_bus_tasks.discard)
            self._agent_bus_tasks.add(task)
        except RuntimeError:
            # No running loop — fire-and-forget delivery is unavailable. This
            # is expected in synchronous test contexts. We log at DEBUG (not
            # silent) so the gap is observable; P1 (Event Log = truth) is not
            # violated because storage has already committed the event.
            logger.debug(
                "AgentBus dispatch skipped (no running loop) for %s "
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
        future = self._pending_commands.pop(key, None)
        if future is not None and not future.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            # Use a nested function instead of lambda for mypy type inference
            def _resolve_pending(f: "asyncio.Future", e: Event) -> None:
                if not f.done():
                    f.set_result(e)
            loop.call_soon_threadsafe(_resolve_pending, future, event)

        # Background tasks: Failed also resolves Requested → Completed waiters.
        if event.type == "BackgroundTaskFailed" and event.correlation_id:
            fail_key = (event.correlation_id, "BackgroundTaskCompleted")
            fail_future = self._pending_commands.pop(fail_key, None)
            if fail_future is not None and not fail_future.done():
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
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

    @staticmethod
    def _parse_approval_params(approval: dict[str, Any]) -> dict[str, Any]:
        raw = approval.get("params") or "{}"
        if isinstance(raw, str):
            return json.loads(raw)
        return dict(raw)

    def _consume_pre_approved(
        self,
        approval_id: str,
        name: str,
        args: dict[str, Any],
        *,
        actor: str,
        correlation_id: str | None,
    ) -> dict | None:
        """Verify a pending approval matches this invocation; grant or return error."""
        rows = self.query_state("approvals", id=approval_id)
        if not rows:
            return {"status": "error", "error": f"Approval not found: {approval_id}"}
        approval = rows[0]
        if approval.get("status") != "pending":
            return {
                "status": "error",
                "error": f"Approval not pending: {approval.get('status')}",
            }
        if approval.get("action") != name:
            return {"status": "error", "error": "Approval action does not match capability"}
        try:
            recorded_args = self._parse_approval_params(approval)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "error": "Approval record has invalid params"}
        if recorded_args != args:
            return {"status": "error", "error": "Approval params do not match capability args"}
        self.grant_approval(
            approval_id,
            action=name,
            actor=actor,
            reason="pre_approved",
            correlation_id=correlation_id,
        )
        return None

    def _handler_execution_exists(self, execution_id: str) -> bool:
        with self._db.get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM handler_executions WHERE id = ? LIMIT 1",
                (execution_id,),
            ).fetchone()
        return row is not None

    async def invoke_capability(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
        caused_by: str | None = None,
        pre_approved: bool = False,
        approval_id: str | None = None,
        principal: Any | None = None,
        execution_id: str | None = None,
    ) -> dict:
        """Invoke a capability through the Kernel, with approval gating.

        ADR-0007 Step 9: authorization is delegated to CapabilityGateway,
        which uses typed Principal (Step 8) for identity-based checks.

        Execution Ownership: when execution_id is provided, this
        capability invocation is attributed to the owning Execution aggregate,
        linking capability events to the Execution via caused_by.
        """
        args = args or {}
        from app.core.harness.mcp_hub import mcp_hub
        from app.core.runtime.capability_decision import capability_gateway
        from app.core.runtime.identity_resolver import identity_resolver

        tool = mcp_hub.get_tool(name)
        if tool is None:
            return {"status": "error", "error": f"Unknown capability: {name}"}

        # Resolve Principal (Step 8): use provided principal or resolve from actor
        if principal is None:
            principal = identity_resolver.resolve(actor, self)

        from app.core.runtime.execution_scope import (
            actor_requires_execution_ownership,
            get_current_execution_id,
        )

        resolved_execution_id = execution_id or get_current_execution_id()
        if resolved_execution_id == "":
            resolved_execution_id = None

        if actor_requires_execution_ownership(actor) and not resolved_execution_id:
            self.emit_event(
                type="CapabilityDenied",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "reason": "missing_execution_id"},
                actor=principal.actor,
                correlation_id=correlation_id,
            )
            return {"status": "error", "error": "missing_execution_id"}

        if resolved_execution_id:
            if not self._handler_execution_exists(resolved_execution_id):
                self.emit_event(
                    type="CapabilityDenied",
                    aggregate_type="capability",
                    aggregate_id=f"cap_{name}",
                    payload={"name": name, "reason": "invalid_execution_id"},
                    actor=principal.actor,
                    correlation_id=correlation_id,
                )
                return {"status": "error", "error": "invalid_execution_id"}

        # Link capability events to the owning Execution when available.
        capability_caused_by = resolved_execution_id or caused_by

        # Unified authorization decision (Step 9)
        decision = capability_gateway.decide(
            principal,
            name,
            args,
            self,
            correlation_id=correlation_id,
            pre_approved=pre_approved,
            approval_id=approval_id,
            execution_id=resolved_execution_id,
        )

        if decision.decision == "deny":
            self.emit_event(
                type="CapabilityDenied",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "reason": decision.reason},
                actor=principal.actor,
                correlation_id=correlation_id,
            )
            # Use the decision reason directly as the error message to
            # preserve backward-compatible error strings from _consume_pre_approved.
            return {"status": "error", "error": decision.reason}

        if decision.decision == "defer":
            self.emit_event(
                type="CapabilityDeferred",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={
                    "name": name,
                    "args_summary": str(args)[:200],
                    "reason": decision.reason,
                    "approval_id": decision.approval_id,
                },
                actor=principal.actor,
                caused_by=capability_caused_by,
                correlation_id=correlation_id,
            )
            return {"status": "pending", "approval_id": decision.approval_id}

        # Decision is "allow" — execute the tool
        try:
            result_str = await mcp_hub.invoke_tool(name, args)

            self.emit_event(
                type="CapabilityInvoked",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "args_summary": str(args)[:200], "result_summary": str(result_str)[:200]},
                actor=principal.actor,
                caused_by=capability_caused_by,
                correlation_id=correlation_id,
            )
            if correlation_id:
                from app.core.runtime.taint import is_external_ingestion_tool, taint_registry

                if is_external_ingestion_tool(name):
                    taint_registry.mark(
                        correlation_id,
                        source="external_ingestion",
                        reason=name,
                    )
            return {"status": "success", "result": result_str}
        except Exception as exc:
            self.emit_event(
                type="CapabilityFailed",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "error": str(exc)},
                actor=principal.actor,
                caused_by=capability_caused_by,
                correlation_id=correlation_id,
            )
            return {"status": "error", "error": str(exc)}

    # --- Task & Agent lifecycle -----------------------------------------------

    def metrics(self) -> dict[str, int]:
        """Return runtime health/counters for observability."""
        return {
            "registry_instances": len(self.agent_registry._instances),
        }

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

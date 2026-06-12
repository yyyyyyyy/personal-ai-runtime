"""The Kernel — the boundary of the Personal AI Runtime.

This is Kernel Space. It alone touches storage. Everything in User Space
(agents, workflows, APIs, UI) must go through this ABI and may never read or
write the database directly.

This module implements the core P0 ABI from docs/RUNTIME_SPEC.md §3.1:
    emit_event / read_events / subscribe_events / query_state

Governance (approval workflows) → kernel_governance.py (GovernanceMixin)
Sovereignty (export/import/rebuild) → kernel_sovereignty.py (SovereigntyMixin)
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

from . import projectors
from .constants import (
    MEMORY_INDEX_EVENT_TYPES,
)
from .event import Event
from .kernel_governance import GovernanceMixin
from .kernel_sovereignty import SovereigntyMixin

logger = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]

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
    aggregate_type   TEXT PRIMARY KEY,
    last_applied_seq INTEGER NOT NULL,
    snapshot_json    TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
"""

MEMORIES_LEGACY_DDL = [
    "ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.5",
    "ALTER TABLE memories ADD COLUMN derived_from_event TEXT",
    "ALTER TABLE memories ADD COLUMN decayed_at DATETIME",
    "ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'",
    "ALTER TABLE memories ADD COLUMN origin TEXT DEFAULT 'claim'",
    "ALTER TABLE memories ADD COLUMN claim_status TEXT",
]


class Kernel(GovernanceMixin, SovereigntyMixin):
    def __init__(self, db=None):
        # Default to the global Database singleton; tests inject their own.
        if db is None:
            from app.store.database import db as global_db

            db = global_db
        self._db = db
        self._subscribers: list[tuple[dict, Subscriber]] = []
        # Process-local ephemeral agent registry — NOT authoritative.
        # Used only for in-flight capability isolation; lost on restart and not
        # reconstructible from the Event Log. Do not rely on it across requests.
        self._active_agents: dict[str, dict] = {}
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Run Alembic migrations; fall back to raw DDL for test/custom DBs."""
        try:
            from app.store.alembic_runner import run_migrations

            run_migrations()
            return
        except Exception as exc:
            logger.warning("Alembic migrations unavailable, using raw DDL: %s", exc)

        with self._db.get_db() as conn:
            conn.executescript(EVENT_LOG_SCHEMA)
            conn.executescript(PROJECTION_CHECKPOINTS_SCHEMA)
            for stmt in MEMORIES_LEGACY_DDL:
                try:
                    conn.execute(stmt)
                except Exception:
                    logger.warning("Legacy DDL statement failed (may be expected): %s", stmt[:80])

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
        except Exception as exc:
            logger.warning(
                "Memory index sync failed for %s (%s): %s",
                event.aggregate_id,
                event.type,
                exc,
            )

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
    ) -> list[Event]:
        """Read the log (pull). Foundation for replay, projection, audit."""
        clauses = ["seq > ?"]
        params: list[Any] = [since_seq]
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
        where = " AND ".join(clauses)
        order_sql = "seq DESC" if order == "desc" else "seq ASC"
        limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
        with self._db.get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log WHERE {where} ORDER BY {order_sql}{limit_sql}",
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

    # --- Read layer (projections) -------------------------------------------

    def query_state(self, selector: str, **filters: Any) -> list[dict]:
        """Read current State (a projection). Returns list of dict rows.

        Each dict follows the schema of the corresponding projection table.
        See kernel/types.py for the intended TypedDict shapes.
        """
        if selector == "goals":
            return self._query_goals(filters)
        if selector == "tasks":
            return self._query_tasks(filters)
        if selector == "approvals":
            return self._query_approvals(filters)
        if selector == "actions":
            return self._query_actions(filters)
        if selector == "memories":
            return self._query_memories(filters)
        if selector == "patterns":
            return self._query_patterns(filters)
        raise ValueError(f"Unknown state selector: {selector!r}")

    def _query_goals(self, filters: dict[str, Any]) -> list[dict]:
        goal_id = filters.get("id")
        status = filters.get("status")
        limit = filters.get("limit", 50)
        order = filters.get("order", "importance_desc")
        last_activity_older_than_days = filters.get("last_activity_older_than_days")
        deadline_within_days = filters.get("deadline_within_days")
        updated_since = filters.get("updated_since")
        has_deadline = filters.get("has_deadline")

        order_clauses = {
            "importance_desc": "importance DESC, created_at DESC",
            "importance_urgency_desc": "importance DESC, urgency DESC",
            "last_activity_asc": "last_activity_at ASC",
            "importance_desc_only": "importance DESC",
        }
        order_sql = order_clauses.get(order, order_clauses["importance_desc"])

        with self._db.get_db() as conn:
            if goal_id:
                row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if last_activity_older_than_days is not None:
                clauses.append("last_activity_at < datetime('now', ?)")
                params.append(f"-{int(last_activity_older_than_days)} days")
            if deadline_within_days is not None:
                clauses.append(
                    "deadline IS NOT NULL AND deadline BETWEEN datetime('now') AND datetime('now', ?)"
                )
                params.append(f"+{int(deadline_within_days)} days")
            if updated_since is not None:
                clauses.append("updated_at >= ?")
                params.append(updated_since)
            if has_deadline:
                clauses.append("deadline IS NOT NULL")

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM goals{where} ORDER BY {order_sql} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_actions(self, filters: dict[str, Any]) -> list[dict]:
        goal_id = filters.get("goal_id")
        action_id = filters.get("id")
        status = filters.get("status")
        limit = filters.get("limit", 100)
        order = filters.get("order", "created_at_asc")

        order_clauses = {
            "created_at_asc": "created_at ASC",
            "created_at_desc": "created_at DESC",
        }
        order_sql = order_clauses.get(order, order_clauses["created_at_asc"])

        with self._db.get_db() as conn:
            if action_id:
                row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if goal_id is not None:
                clauses.append("goal_id = ?")
                params.append(goal_id)
            if status is not None:
                clauses.append("status = ?")
                params.append(status)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM actions{where} ORDER BY {order_sql} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_tasks(self, filters: dict[str, Any]) -> list[dict]:
        task_id = filters.get("id")
        status = filters.get("status")
        parent_goal_id = filters.get("parent_goal_id")
        parent_task_id = filters.get("parent_task_id")
        root_only = filters.get("root_only")
        depends_on_task = filters.get("depends_on_task")
        limit = filters.get("limit")
        order = filters.get("order", "created_at_asc")

        order_clauses = {
            "created_at_asc": "created_at ASC",
            "created_at_desc": "created_at DESC",
            "priority_desc": "priority DESC, created_at ASC",
            "priority_desc_created_desc": "priority DESC, created_at DESC",
        }
        order_sql = order_clauses.get(order, order_clauses["created_at_asc"])

        with self._db.get_db() as conn:
            if task_id:
                row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if parent_goal_id is not None:
                clauses.append("parent_goal_id = ?")
                params.append(parent_goal_id)
            if parent_task_id is not None:
                clauses.append("parent_task_id = ?")
                params.append(parent_task_id)
            if root_only:
                clauses.append("parent_task_id IS NULL")
            if depends_on_task is not None:
                clauses.append("dependencies_json LIKE ?")
                params.append(f"%{depends_on_task}%")

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
            rows = conn.execute(
                f"SELECT * FROM tasks{where} ORDER BY {order_sql}{limit_sql}",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_approvals(self, filters: dict[str, Any]) -> list[dict]:
        approval_id = filters.get("id")
        status = filters.get("status")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if approval_id:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return [dict(row)] if row else []
            if status is not None:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def _query_memories(self, filters: dict[str, Any]) -> list[dict]:
        memory_id = filters.get("id")
        category = filters.get("category")
        origin = filters.get("origin")
        claim_status = filters.get("claim_status")
        confidence_gt = filters.get("confidence_gt")
        confidence_lt = filters.get("confidence_lt")
        decay_eligible = filters.get("decay_eligible")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if memory_id:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ?", (memory_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if category is not None:
                clauses.append("category = ?")
                params.append(category)
            if origin is not None:
                clauses.append("origin = ?")
                params.append(origin)
            if claim_status is not None:
                clauses.append("claim_status = ?")
                params.append(claim_status)
            if confidence_gt is not None:
                clauses.append("confidence > ?")
                params.append(confidence_gt)
            if confidence_lt is not None:
                clauses.append("confidence < ?")
                params.append(confidence_lt)
            if decay_eligible:
                clauses.append(
                    "(decayed_at IS NULL OR decayed_at < datetime('now', '-7 days'))"
                )

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM memories{where} ORDER BY confidence DESC, created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_patterns(self, filters: dict[str, Any]) -> list[dict]:
        """Read statistical patterns (time_distribution, topic_distribution, trend).

        Filters supported: pattern_type, metric, window_days, limit.
        """
        pattern_id = filters.get("id")
        pattern_type = filters.get("pattern_type")
        metric = filters.get("metric")
        window_days = filters.get("window_days")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if pattern_id:
                row = conn.execute(
                    "SELECT * FROM patterns WHERE id = ?", (pattern_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if pattern_type is not None:
                clauses.append("pattern_type = ?")
                params.append(pattern_type)
            if metric is not None:
                clauses.append("metric = ?")
                params.append(metric)
            if window_days is not None:
                clauses.append("window_days = ?")
                params.append(int(window_days))

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM patterns{where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def list_capability_definitions(self) -> list[dict]:
        """Read-only capability metadata for LLM tool schemas (User Space ABI)."""
        from app.core.harness.mcp_hub import mcp_hub

        return mcp_hub.get_tool_defs_for_llm()

    def recall_memory(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from derived memories (projected from MemoryDerived events).

        Uses ChromaDB under the hood, but User Space never touches the vector
        store directly — it all flows through this ABI.
        """
        from app.store.vector import vector_store

        return vector_store.search_memories(query, n_results=k)

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

    async def invoke_capability(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
        caused_by: str | None = None,
        pre_approved: bool = False,
        approval_id: str | None = None,
    ) -> dict:
        """Invoke a capability through the Kernel, with approval gating.

        All external-world interactions go through here. The capability is
        executed only if the risk policy allows it (auto_approve) or the
        approval was previously granted.
        """
        args = args or {}
        from app.core.harness.mcp_hub import mcp_hub
        from app.core.runtime.capability_policy import capability_policy
        from app.core.runtime.sensitive_router import sensitive_router

        tool = mcp_hub.get_tool(name)
        if tool is None:
            return {"status": "error", "error": f"Unknown capability: {name}"}

        # Agent isolation: check allowed_capabilities whitelist
        if actor.startswith("agent:"):
            agent_id = actor.split(":", 1)[1]
            agent_ctx = self._active_agents.get(agent_id)
            if agent_ctx:
                allowed = agent_ctx.get("allowed_capabilities", ["*"])
                if "*" not in allowed and name not in allowed:
                    self.emit_event(
                        type="CapabilityDenied",
                        aggregate_type="capability",
                        aggregate_id=f"cap_{name}",
                        payload={"name": name, "reason": "agent_not_authorized"},
                        actor=actor,
                        correlation_id=correlation_id,
                    )
                    return {"status": "error", "error": f"Agent not authorized for: {name}"}

        policy_risk = capability_policy.risk_for(name, mcp_hub.needs_confirmation(name))
        if policy_risk == "forbidden":
            self.emit_event(
                type="CapabilityDenied",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "reason": "forbidden_by_policy"},
                actor=actor,
                correlation_id=correlation_id,
            )
            return {"status": "error", "error": f"Capability forbidden: {name}"}

        if pre_approved:
            if not approval_id:
                return {"status": "error", "error": "pre_approved requires approval_id"}
            pre_err = self._consume_pre_approved(
                approval_id,
                name,
                args,
                actor=actor,
                correlation_id=correlation_id,
            )
            if pre_err is not None:
                return pre_err

        if not pre_approved:
            from app.core.runtime.taint import is_write_class_tool, taint_registry

            risk = sensitive_router.elevated_risk(name, args) or (
                "high" if policy_risk == "high" else "low"
            )
            if (
                correlation_id
                and taint_registry.is_tainted(correlation_id)
                and is_write_class_tool(name)
            ):
                risk = "high"
            approval = self.request_approval(
                action=name,
                risk=risk,
                ctx={"args": args},
                actor=actor,
                correlation_id=correlation_id,
            )

            if approval["status"] != "approved":
                self.emit_event(
                    type="CapabilityDeferred",
                    aggregate_type="capability",
                    aggregate_id=f"cap_{name}",
                    payload={
                        "name": name,
                        "args_summary": str(args)[:200],
                        "reason": approval.get("reason", "needs_user_confirmation"),
                        "approval_id": approval["approval_id"],
                    },
                    actor=actor,
                    caused_by=caused_by,
                    correlation_id=correlation_id,
                )
                return {"status": "pending", "approval_id": approval["approval_id"]}

        # Auto-allowed or pre-granted: execute the tool (mcp_hub handles
        # sync/async dispatch and telemetry; it is properly typed as async).
        try:
            result_str = await mcp_hub.invoke_tool(name, args)

            self.emit_event(
                type="CapabilityInvoked",
                aggregate_type="capability",
                aggregate_id=f"cap_{name}",
                payload={"name": name, "args_summary": str(args)[:200], "result_summary": str(result_str)[:200]},
                actor=actor,
                caused_by=caused_by,
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
                actor=actor,
                caused_by=caused_by,
                correlation_id=correlation_id,
            )
            return {"status": "error", "error": str(exc)}

    # --- Task & Agent lifecycle -----------------------------------------------

    def create_task(
        self,
        name: str,
        plan: dict[str, Any] | None = None,
        parent_goal_id: str | None = None,
        parent_task_id: str | None = None,
        priority: int = 0,
        dependencies: list[str] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        """Register a task as a schedulable unit of work. Emits TaskCreated."""
        tid = task_id or f"task_{uuid.uuid4().hex}"
        deps_json = json.dumps(dependencies) if dependencies else None
        self.emit_event(
            type="TaskCreated",
            aggregate_type="task",
            aggregate_id=tid,
            payload={
                "name": name,
                "description": plan.get("summary", "") if plan else "",
                "parent_goal_id": parent_goal_id,
                "parent_task_id": parent_task_id,
                "priority": priority if plan is None else plan.get("priority", priority),
                "dependencies_json": deps_json,
            },
            actor=actor,
            correlation_id=correlation_id,
        )
        return {"task_id": tid, "status": "pending"}

    def change_task_status(
        self,
        task_id: str,
        status: str,
        actor: str = "system",
        correlation_id: str | None = None,
    ) -> None:
        """Emit TaskStatusChanged for generic status transitions."""
        self.emit_event(
            type="TaskStatusChanged",
            aggregate_type="task",
            aggregate_id=task_id,
            payload={"status": status},
            actor=actor,
            correlation_id=correlation_id,
        )

    def spawn_agent(
        self,
        spec: str,
        task_ref: str,
        actor: str = "kernel",
        correlation_id: str | None = None,
        allowed_capabilities: list[str] | None = None,
    ) -> dict:
        """Spawn a temporary agent to work on a task. Emits AgentSpawned.

        The agent is ephemeral — it must be kill_agent'd after completing.
        `spec` identifies the agent type (e.g. "planner", "critic", "brain").

        `_active_agents` tracks allowed_capabilities for the spawned agent only
        for the current process lifetime; the whitelist does not survive restart.
        """
        agent_id = f"agent_{uuid.uuid4().hex}"
        # Mark task as started
        self.emit_event(
            type="TaskStarted",
            aggregate_type="task",
            aggregate_id=task_ref,
            payload={"agent_id": agent_id, "spec": spec},
            actor=actor,
            correlation_id=correlation_id,
        )
        self.emit_event(
            type="AgentSpawned",
            aggregate_type="task",
            aggregate_id=agent_id,
            payload={"spec": spec, "task_ref": task_ref},
            actor=actor,
            correlation_id=correlation_id,
        )
        handle = {"agent_id": agent_id, "task_ref": task_ref, "spec": spec}
        self._active_agents[agent_id] = {
            "spec": spec,
            "task_ref": task_ref,
            "allowed_capabilities": allowed_capabilities or ["*"],
        }
        return handle

    def kill_agent(
        self,
        handle: dict,
        result: dict[str, Any] | None = None,
        actor: str = "kernel",
        correlation_id: str | None = None,
    ) -> None:
        """Destroy an ephemeral agent and complete its task.

        Emits AgentTerminated and TaskCompleted (or TaskFailed).
        Removes the agent from the non-authoritative in-process `_active_agents`
        map; this state is not persisted to the Event Log.
        """
        agent_id = handle["agent_id"]
        task_ref = handle["task_ref"]
        failed = result and result.get("status") == "error"
        self.emit_event(
            type="AgentTerminated",
            aggregate_type="task",
            aggregate_id=agent_id,
            payload={"task_ref": task_ref, "result": result},
            actor=actor,
            correlation_id=correlation_id,
        )
        task_type = "TaskFailed" if failed else "TaskCompleted"
        self.emit_event(
            type=task_type,
            aggregate_type="task",
            aggregate_id=task_ref,
            payload=result or {},
            actor=actor,
            correlation_id=correlation_id,
        )
        self._active_agents.pop(agent_id, None)

    # --- Data sovereignty (export / import / rebuild) -----------------------

    # See kernel_sovereignty.py for:
    #   export_event_log_rows() / import_event_log_rows() / table_counts()
    #   bootstrap_chat_from_snapshot() / export_chat_rows()
    #   rebuild() / rebuild_all()
    #   save_projection_snapshot() / save_projection_snapshots()
    #   _drop_event_log_guards() / _ensure_event_log_guards()
    #   _restore_table_snapshot()

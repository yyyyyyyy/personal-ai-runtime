"""The Kernel — the boundary of the Personal AI Runtime.

This is Kernel Space. It alone touches storage. Everything in User Space
(agents, workflows, APIs, UI) must go through this ABI and may never read or
write the database directly.

This module implements the minimal P0 ABI from RUNTIME_SPEC.md §3.1:
    emit_event / read_events / subscribe_events / query_state
plus `rebuild`, which proves the core invariant:
    State is a projection of the Event Log and can be reconstructed from it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from . import projectors
from .event import Event

# Append-only, ordered, immutable Event Log.
# `seq` is a monotonic ordinal (the source of truth for ordering — not `ts`).
# Triggers enforce immutability at the storage layer: the log can only grow.
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

Subscriber = Callable[[Event], None]


class Kernel:
    def __init__(self, db=None):
        # Default to the global Database singleton; tests inject their own.
        if db is None:
            from app.store.database import db as global_db

            db = global_db
        self._db = db
        self._subscribers: list[tuple[dict, Subscriber]] = []
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._db.get_db() as conn:
            conn.executescript(EVENT_LOG_SCHEMA)
            # Migrate legacy memories table for derived-belief support
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.5")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN derived_from_event TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN decayed_at DATETIME")
            except Exception:
                pass

    # --- Truth layer ---------------------------------------------------------

    def emit_event(
        self,
        type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
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

        self._dispatch(event)
        return event

    def read_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        type: str | None = None,
        correlation_id: str | None = None,
        since_seq: int = 0,
    ) -> list[Event]:
        """Read the log in order (pull). Foundation for replay, projection, audit."""
        clauses = ["seq > ?"]
        params: list[Any] = [since_seq]
        if aggregate_type is not None:
            clauses.append("aggregate_type = ?")
            params.append(aggregate_type)
        if aggregate_id is not None:
            clauses.append("aggregate_id = ?")
            params.append(aggregate_id)
        if type is not None:
            clauses.append("type = ?")
            params.append(type)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        where = " AND ".join(clauses)
        with self._db.get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log WHERE {where} ORDER BY seq ASC", params
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
            handler(event)

    # --- Read layer (projections) -------------------------------------------

    def query_state(self, selector: str, **filters: Any) -> list[dict]:
        """Read current State (a projection). For this slice: `goals`.

        Kept deliberately small — selectors expand as projections are added.
        """
        if selector == "goals":
            goal_id = filters.get("id")
            status = filters.get("status")
            limit = filters.get("limit", 50)
            with self._db.get_db() as conn:
                if goal_id:
                    row = conn.execute(
                        "SELECT * FROM goals WHERE id = ?", (goal_id,)
                    ).fetchone()
                    return [dict(row)] if row else []
                if status:
                    rows = conn.execute(
                        "SELECT * FROM goals WHERE status = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
                        (status, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM goals ORDER BY importance DESC, created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(r) for r in rows]
        if selector == "tasks":
            with self._db.get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at ASC"
                ).fetchall()
            return [dict(r) for r in rows]
        raise ValueError(f"Unknown state selector: {selector!r}")

    def recall_memory(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from derived memories (projected from MemoryDerived events).

        Uses ChromaDB under the hood, but User Space never touches the vector
        store directly — it all flows through this ABI.
        """
        from app.store.vector import vector_store

        return vector_store.search_memories(query, n_results=k)

    # --- Governance layer ----------------------------------------------------

    def request_approval(
        self,
        action: str,
        risk: str = "low",
        ctx: dict[str, Any] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
    ) -> dict:
        """Request approval for a capability invocation. Returns a decision dict.

        Risk policy (from MCPHub.needs_confirmation):
          - "low"  → auto_allow, emit ApprovalGranted immediately
          - "high" → needs_user, emit ApprovalRequested and return pending
        """
        approval_id = f"apr_{uuid.uuid4().hex}"

        self.emit_event(
            type="ApprovalRequested",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": action, "risk": risk, "ctx": ctx or {}},
            actor=actor,
            correlation_id=correlation_id,
        )

        if risk == "low":
            self.emit_event(
                type="ApprovalGranted",
                aggregate_type="approval",
                aggregate_id=approval_id,
                payload={"action": action, "reason": "auto_allow"},
                actor="kernel",
                correlation_id=correlation_id,
            )
            return {"status": "approved", "approval_id": approval_id}
        else:
            return {"status": "pending", "approval_id": approval_id, "reason": "needs_user_confirmation"}

    async def invoke_capability(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        actor: str = "system",
        correlation_id: str | None = None,
        caused_by: str | None = None,
    ) -> dict:
        """Invoke a capability through the Kernel, with approval gating.

        All external-world interactions go through here. The capability is
        executed only if the risk policy allows it (auto_approve) or the
        approval was previously granted.
        """
        args = args or {}
        from app.core.harness.mcp_hub import mcp_hub

        tool = mcp_hub.get_tool(name)
        if tool is None:
            return {"status": "error", "error": f"Unknown capability: {name}"}

        risk = "high" if mcp_hub.needs_confirmation(name) else "low"
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
    ) -> dict:
        """Spawn a temporary agent to work on a task. Emits AgentSpawned.
        The agent is ephemeral — it must be kill_agent'd after completing.
        `spec` identifies the agent type (e.g. "planner", "critic", "brain").
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
        return {"agent_id": agent_id, "task_ref": task_ref, "spec": spec}

    def kill_agent(
        self,
        handle: dict,
        result: dict[str, Any] | None = None,
        actor: str = "kernel",
        correlation_id: str | None = None,
    ) -> None:
        """Destroy an ephemeral agent and complete its task.
        Emits AgentTerminated and TaskCompleted (or TaskFailed).
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

    # --- Replay / rebuild ----------------------------------------------------

    def rebuild(self, aggregate_type: str) -> int:
        """Wipe the projection(s) for an aggregate type and rebuild from the Event
        Log. Returns the number of events replayed.

        This is the proof of the Runtime's core property: State is fully derived
        from the immutable Event Log. The Event Log itself is never touched here.
        """
        tables = projectors.owned_tables(aggregate_type)
        events = self.read_events(aggregate_type=aggregate_type)
        with self._db.get_db() as conn:
            for table in tables:
                conn.execute(f"DELETE FROM {table}")
            for event in events:
                projectors.apply(event, conn)
        return len(events)

    def rebuild_all(self) -> dict[str, int]:
        """Rebuild all registered aggregate types. Returns {type: count}."""
        result = {}
        for at in list(projectors._OWNED_TABLES):
            result[at] = self.rebuild(at)
        return result

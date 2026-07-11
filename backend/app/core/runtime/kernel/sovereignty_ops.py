# mypy: disable-error-code="attr-defined"
"""Sovereignty operations — export, import, rebuild, erase.

Extracted from ``kernel_sovereignty.SovereigntyMixin`` so the God Object
LOC budget can shrink. Functions take a Kernel-like object (``_db``,
``emit_event``, ``read_events``, ``_sync_memory_index``, …).
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import projectors_registry as projectors
from .constants import (
    CHAT_EVENT_TYPES,
    MEMORY_INDEX_EVENT_TYPES,
    PROJECTION_SNAPSHOT_AGGREGATES,
)
from .query_builder import (
    fetch_chat_projection_dicts,
    fetch_event_log_dicts,
    iter_snapshot_document_bytes,
)

EXPORT_FORMAT = "snapshot"


def all_projection_tables() -> set[str]:
    result: set[str] = set()
    for tables in projectors._OWNED_TABLES.values():
        result.update(tables)
    return result



def _drop_event_log_guards(kernel, conn) -> None:
    conn.execute("DROP TRIGGER IF EXISTS event_log_no_update")
    conn.execute("DROP TRIGGER IF EXISTS event_log_no_delete")

def _ensure_event_log_guards(kernel, conn) -> None:
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS event_log_no_update
           BEFORE UPDATE ON event_log
           BEGIN SELECT RAISE(ABORT, 'event_log is append-only: UPDATE forbidden'); END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS event_log_no_delete
           BEFORE DELETE ON event_log
           BEGIN SELECT RAISE(ABORT, 'event_log is append-only: DELETE forbidden'); END"""
    )

def export_event_log_rows(kernel, *, conn=None) -> list[dict[str, Any]]:
    """Export full event_log for lossless snapshot (batched seq cursor).

    When ``conn`` is provided, reads on that connection so callers can
    hold a single point-in-time transaction across event_log + chat.
    """
    if conn is not None:
        return fetch_event_log_dicts(conn)
    with kernel._db.get_db() as owned:
        return fetch_event_log_dicts(owned)

def import_event_log_rows(
    kernel,
    rows: list[dict[str, Any]],
    *,
    rebuild_projections: bool = True,
) -> int:
    """Bulk-import events preserving seq/id; optionally rebuild all projections.

    DESTRUCTIVE OPERATION: This drops event_log guards, clears event_log
    and all projection tables, then rewrites them. If rebuild_projections
    fails mid-way, some projection tables may be left empty. Callers
    should take a file-level backup before invoking this method.

    For atomic import+rebuild, wrap in a single connection context
    (TODO: Phase 3 architectural improvement).
    """
    with kernel._db.get_db() as conn:
        _drop_event_log_guards(kernel, conn)
        for table in all_projection_tables():
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM event_log")

        for row in sorted(rows, key=lambda r: int(r["seq"])):
            payload = row.get("payload")
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            conn.execute(
                """INSERT INTO event_log
                   (seq, id, type, aggregate_type, aggregate_id, actor, payload,
                    caused_by, correlation_id, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(row["seq"]),
                    row["id"],
                    row["type"],
                    row["aggregate_type"],
                    row["aggregate_id"],
                    row["actor"],
                    payload,
                    row.get("caused_by"),
                    row.get("correlation_id"),
                    row["ts"],
                ),
            )

        max_seq = max((int(r["seq"]) for r in rows), default=0)
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'event_log'")
        if max_seq > 0:
            conn.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES ('event_log', ?)",
                (max_seq,),
            )
        _ensure_event_log_guards(kernel, conn)

    if rebuild_projections:
        rebuild_all(kernel)
        for event in kernel.read_events(types=list(MEMORY_INDEX_EVENT_TYPES)):
            kernel._sync_memory_index(event)
    return len(rows)

def table_counts(kernel, tables: tuple[str, ...]) -> dict[str, int]:
    """Kernel-space row counts for sovereignty verification.

    Tolerates dropped tables (e.g. goals was dropped in v06) by returning 0
    instead of raising — callers that still reference legacy table names
    get a sensible default during the migration window.
    """
    out: dict[str, int] = {}
    with kernel._db.get_db() as conn:
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                out[table] = int(row["c"])
            except Exception:
                out[table] = 0
    return out

def count_events(kernel, aggregate_type: str) -> int:
    """Count events in event_log filtered by aggregate_type (kernel-space)."""
    with kernel._db.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM event_log WHERE aggregate_type = ?",
            (aggregate_type,),
        ).fetchone()
        return int(row["c"])

def bootstrap_chat_from_snapshot(
    kernel,
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Emit chat events for legacy snapshots."""
    has_chat_events = any(
        r.get("type") in CHAT_EVENT_TYPES for r in event_rows
    )
    if has_chat_events:
        return {"conversations": 0, "messages": 0}

    conv_count = 0
    msg_count = 0
    for conv in conversations:
        kernel.emit_event(
            "ConversationCreated",
            "conversation",
            conv["id"],
            payload={
                "title": conv.get("title", "New Conversation"),
                "summary": conv.get("summary"),
                "created_at": conv.get("created_at"),
            },
            actor="import",
        )
        conv_count += 1

    for msg in messages:
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None and isinstance(tool_calls, str):
            try:
                tool_calls = json.loads(tool_calls)
            except json.JSONDecodeError:
                pass
        kernel.emit_event(
            "MessageAppended",
            "conversation",
            msg["conversation_id"],
            payload={
                "message_id": msg["id"],
                "role": msg["role"],
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
                "tool_call_id": msg.get("tool_call_id"),
                "created_at": msg.get("created_at"),
            },
            actor="import",
        )
        msg_count += 1

    return {"conversations": conv_count, "messages": msg_count}

def export_chat_rows(
    kernel, *, conn=None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Export conversation/message projections (denormalized backup)."""
    if conn is not None:
        return fetch_chat_projection_dicts(conn)
    with kernel._db.get_db() as owned:
        return fetch_chat_projection_dicts(owned)

def _checkpoint_seq(kernel, agent_id: str, aggregate_type: str) -> int:
    """Return the last_applied_seq for a per-agent checkpoint (0 if none)."""
    with kernel._db.get_db() as conn:
        row = conn.execute(
            "SELECT last_applied_seq FROM projection_checkpoints "
            "WHERE agent_id = ? AND aggregate_type = ?",
            (agent_id, aggregate_type),
        ).fetchone()
    return int(row["last_applied_seq"]) if row else 0

def _restore_table_snapshot(kernel, conn, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ",".join("?" * len(columns))
    col_sql = ",".join(columns)
    for row in rows:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({col_sql}) VALUES ({placeholders})",
            [row[c] for c in columns],
        )

def save_projection_snapshot(
    kernel,
    aggregate_type: str,
    agent_id: str = "kernel",
) -> dict[str, Any]:
    """Persist projection tables + last_applied_seq for incremental rebuild.

    agent_id defaults to 'kernel' for global (non-agent) projections.
    Per-agent snapshots use the agent's instance id.
    """
    from datetime import UTC, datetime

    tables = projectors.owned_tables(aggregate_type)
    events = kernel.read_events(aggregate_type=aggregate_type)
    last_seq = max((int(e.seq) for e in events if e.seq is not None), default=0)

    snapshot: dict[str, list[dict[str, Any]]] = {}
    with kernel._db.get_db() as conn:
        for table in tables:
            snapshot[table] = [
                dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()
            ]
        conn.execute(
            """INSERT OR REPLACE INTO projection_checkpoints
               (agent_id, aggregate_type, last_applied_seq, snapshot_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                agent_id,
                aggregate_type,
                last_seq,
                json.dumps(snapshot),
                datetime.now(UTC).isoformat(),
            ),
        )
    return {
        "agent_id": agent_id,
        "aggregate_type": aggregate_type,
        "last_applied_seq": last_seq,
    }

def save_projection_snapshots(
    kernel,
    aggregate_types: tuple[str, ...] | list[str] | None = None,
    agent_id: str = "kernel",
) -> list[dict[str, Any]]:
    """Persist checkpoints for one or more aggregates."""
    types = aggregate_types or PROJECTION_SNAPSHOT_AGGREGATES
    return [save_projection_snapshot(kernel, agg, agent_id=agent_id) for agg in types]

def rebuild(
    kernel,
    aggregate_type: str,
    agent_id: str = "kernel",
) -> int:
    """Rebuild projection from Event Log (incremental when checkpoint exists).

    agent_id defaults to 'kernel' for global projections.
    Per-agent rebuilds restore agent-specific state from the checkpoint.
    """
    tables = projectors.owned_tables(aggregate_type)
    events = kernel.read_events(aggregate_type=aggregate_type)
    with kernel._db.get_db() as conn:
        checkpoint = conn.execute(
            "SELECT last_applied_seq, snapshot_json FROM projection_checkpoints "
            "WHERE agent_id = ? AND aggregate_type = ?",
            (agent_id, aggregate_type),
        ).fetchone()

        delete_order = list(reversed(tables))
        for table in delete_order:
            conn.execute(f"DELETE FROM {table}")

        last_seq = 0
        if checkpoint:
            last_seq = int(checkpoint["last_applied_seq"])
            snapshot = json.loads(checkpoint["snapshot_json"])
            for table in tables:
                _restore_table_snapshot(kernel, conn, table, snapshot.get(table, []))

        replayed = 0
        for event in events:
            if event.seq is not None and int(event.seq) <= last_seq:
                continue
            projectors.apply(event, conn)
            replayed += 1

    for event in events:
        if checkpoint and event.seq is not None and int(event.seq) <= last_seq:
            continue
        kernel._sync_memory_index(event)
    return replayed if checkpoint else len(events)

def rebuild_all(kernel) -> dict[str, int]:
    """Rebuild all registered aggregate types."""
    result = {}
    for at in list(projectors._OWNED_TABLES):
        result[at] = rebuild(kernel, at)
    return result

def iter_snapshot_json_chunks(kernel):
    """Yield UTF-8 chunks of a lossless snapshot JSON document.

    Streams ``event_log`` row-by-row so the HTTP layer need not hold the
    full serialized body. Wire format matches :meth:`snapshot`.
    """
    now = datetime.now(UTC).isoformat()
    snapshot_id = str(uuid.uuid4())
    with kernel._db.get_db() as conn:
        yield from iter_snapshot_document_bytes(
            conn,
            snapshot_id=snapshot_id,
            exported_at=now,
            export_format=EXPORT_FORMAT,
        )

def snapshot(kernel) -> dict[str, Any]:
    """Export complete personal snapshot as a dict.

    Prefer :meth:`iter_snapshot_json_chunks` for HTTP plaintext export.
    Encrypted export and scripts still use this materialised form.
    """
    return json.loads(b"".join(iter_snapshot_json_chunks(kernel)))

def restore(kernel, snapshot: dict, read_only: bool = True) -> dict[str, Any]:
    """Import snapshot. Write import requires read_only=False.

    This is the kernel-space equivalent of DigitalLegacy.import_all().
    Handles snapshot format, event-log-based import, and legacy goal/memory
    import for older lossy snapshots.
    """
    if read_only:
        return {
            "valid": True,
            "format": snapshot.get("format"),
            "counts": {
                "event_log": len(snapshot.get("event_log", [])),
                "conversations": len(snapshot.get("conversations", [])),
                "messages": len(snapshot.get("messages", [])),
            },
        }

    export_format = snapshot.get("format")
    if export_format == EXPORT_FORMAT or snapshot.get("event_log") is not None:
        return _restore_from_snapshot(kernel, snapshot)
    return _import_legacy_goals_memories(kernel, snapshot)

def _restore_from_snapshot(kernel, snapshot: dict) -> dict:
    """Restore from event_log-based snapshot."""
    event_rows = snapshot.get("event_log", [])
    conversations = snapshot.get("conversations", [])
    messages = snapshot.get("messages", [])

    imported_events = import_event_log_rows(kernel,
        event_rows, rebuild_projections=True
    )

    chat_bootstrapped = bootstrap_chat_from_snapshot(kernel,
        conversations, messages, event_rows
    )

    return {
        "format": EXPORT_FORMAT,
        "events_imported": imported_events,
        "conversations_imported": chat_bootstrapped.get("conversations", 0),
        "messages_imported": chat_bootstrapped.get("messages", 0),
    }

def _import_legacy_goals_memories(kernel, snapshot: dict) -> dict[str, Any]:
    """Best-effort import for older lossy snapshots (goals/memories only)."""
    from app.core.agents.memory_engine import memory_engine
    from app.core.agents.user_profile import user_profile

    result: dict[str, Any] = {
        "format": "legacy",
        "profile_categories": 0,
        "goals_imported": 0,
        "memories_imported": 0,
    }

    profile_data = snapshot.get("profile", {})
    for category, cat_data in profile_data.items():
        if isinstance(cat_data, dict) and "data" in cat_data:
            user_profile.update_profile(
                category,
                cat_data["data"],
                confidence=cat_data.get("confidence", 0.3),
            )
            result["profile_categories"] += 1

    for goal in snapshot.get("goals", []):
        gid = goal.get("id") or str(uuid.uuid4())
        kernel.emit_event(
            "WorkItemCreated",
            "work_item",
            gid,
            payload={
                "title": goal.get("title", ""),
                "description": goal.get("description", ""),
                "status": goal.get("status", "active"),
                "importance": goal.get("importance", 0.5),
                "urgency": goal.get("urgency", 0.5),
            },
            actor="import",
        )
        result["goals_imported"] += 1

    for mem in snapshot.get("memories", []):
        memory_engine.store_memory(
            mem.get("content", ""),
            category=mem.get("category", "fact"),
            source="legacy_import",
            confidence=float(mem.get("confidence", 0.5)),
            actor="import",
        )
        result["memories_imported"] += 1

    return result

def erase(kernel) -> dict:
    """Remove database and vector store files (irreversible).

    This is the kernel-space equivalent of DigitalLegacy.destroy_all().
    After erasing, the Database singleton is reinitialized.
    """
    from app.config import settings

    db_path = Path(settings.sqlite_path)
    vector_path = Path(settings.vector_dir)

    if db_path.exists():
        db_path.unlink()
    if vector_path.exists():
        shutil.rmtree(vector_path, ignore_errors=True)

    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)

    import app.store.database as database_module
    from app.store.database import Database

    database_module.db = Database()

    return {
        "status": "destroyed",
        "message": "All local data removed. Restart the server to reinitialize.",
    }

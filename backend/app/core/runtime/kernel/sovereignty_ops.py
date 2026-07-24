# mypy: disable-error-code="attr-defined"
"""Sovereignty operations — export, import, rebuild, erase.

Extracted from ``kernel_sovereignty.SovereigntyMixin`` so the God Object
LOC budget can shrink. Functions take a Kernel-like object (``_db``,
``emit_event``, ``read_events``, ``_sync_memory_index``, …).
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import projectors_registry as projectors
from .constants import (
    CHAT_EVENT_TYPES,
    PROJECTION_SNAPSHOT_AGGREGATES,
)
from .query_builder import (
    fetch_chat_projection_dicts,
    fetch_event_log_dicts,
    iter_snapshot_document_bytes,
)

logger = logging.getLogger(__name__)

EXPORT_FORMAT = "snapshot"


def _ordered_projection_tables() -> list[str]:
    """Return projection tables in safe DELETE order (children before parents).

    Tables with foreign keys to other projection tables must be cleared first.
    """
    all_tables: set[str] = set()
    for tables in projectors._OWNED_TABLES.values():
        all_tables.update(tables)
    # FK: messages.conversation_id → conversations.id
    # FK (in data): handler_executions may reference event_log seqs (by convention)
    child_before_parent = ["messages", "handler_executions", "timer_events"]
    ordered = []
    for child in child_before_parent:
        if child in all_tables:
            ordered.append(child)
            all_tables.discard(child)
    ordered.extend(sorted(all_tables))
    return ordered



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
    """Import while excluding concurrent vector sync and repair operations."""
    from .memory_index_sync import memory_index_operation_lock

    with memory_index_operation_lock:
        return _import_event_log_rows_locked(
            kernel,
            rows,
            rebuild_projections=rebuild_projections,
        )


def _import_event_log_rows_locked(
    kernel,
    rows: list[dict[str, Any]],
    *,
    rebuild_projections: bool = True,
) -> int:
    """Bulk-import events preserving seq/id; optionally rebuild all projections.

    The entire SQLite operation (clear event_log + projection tables + repair
    queue, insert rows, rebuild projections) runs in a single transaction.
    If any step fails the transaction is rolled back.

    Chroma (external to SQLite) is reconciled *after* commit via a full
    projection↔index sync; failures fall back to the durable repair queue.
    """
    conn = kernel._db.get_raw_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _drop_event_log_guards(kernel, conn)
        for table in _ordered_projection_tables():
            conn.execute(f"DELETE FROM {table}")
        # Checkpoints and snapshot blobs belong to the old event-log generation
        # even when projection replay is intentionally deferred.
        conn.execute("DELETE FROM projection_checkpoints")
        conn.execute("DELETE FROM event_log")
        # Drop stale repair jobs so pre-restore MemoryDeleted tasks cannot
        # delete memories that the restored snapshot reintroduces.
        conn.execute("DELETE FROM memory_index_repairs")

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
                    row.get("ts"),
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
            _rebuild_all_on_conn(kernel, conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if rebuild_projections:
        _reconcile_memory_index_after_restore(kernel)

    return len(rows)


def _rebuild_all_on_conn(kernel, conn) -> dict[str, int]:
    """Rebuild all projections using the supplied connection (within a txn)."""
    result = {}
    for at in list(projectors._OWNED_TABLES):
        result[at] = _rebuild_aggregate_on_conn(kernel, conn, at)
    return result


def _rebuild_aggregate_on_conn(kernel, conn, aggregate_type: str) -> int:
    """Rebuild one aggregate's projections on the given connection."""
    tables = projectors.owned_tables(aggregate_type)
    delete_order = list(reversed(tables))
    for table in delete_order:
        conn.execute(f"DELETE FROM {table}")
    # Clear any checkpoint so the rebuild is from scratch.
    conn.execute(
        "DELETE FROM projection_checkpoints WHERE aggregate_type = ?",
        (aggregate_type,),
    )
    # Read events directly from the same connection.
    rows = conn.execute(
        "SELECT * FROM event_log WHERE aggregate_type = ? ORDER BY seq",
        (aggregate_type,),
    ).fetchall()
    from .event import Event
    replayed = 0
    for row in rows:
        event = Event(
            seq=int(row["seq"]),
            id=row["id"],
            type=row["type"],
            aggregate_type=str(row["aggregate_type"]),
            aggregate_id=row["aggregate_id"],
            actor=row["actor"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            caused_by=row["caused_by"],
            correlation_id=row["correlation_id"],
            ts=row["ts"],
        )
        projectors.apply(event, conn)
        replayed += 1
    return replayed


def _reconcile_memory_index_after_restore(kernel) -> bool:
    """Full Chroma ↔ SQLite memories reconciliation after restore commit.

    Deletes vector entries not present in the restored projection and
    upserts every active memory. Failures are recorded in the durable
    repair queue for RuntimeLoop to retry. Returns False only when the full
    index could not be enumerated and a durable full-reconcile retry is needed.
    """
    from .memory_index_sync import (
        MEMORY_INDEX_RECONCILE_AGGREGATE,
        MEMORY_INDEX_RECONCILE_EVENT,
        persist_memory_index_repair,
    )

    if kernel._memory_index is None:
        return True

    with kernel._db.get_db() as conn:
        rows = conn.execute(
            """SELECT id, content, category, source, status
               FROM memories
               WHERE COALESCE(status, 'active') NOT IN ('deleted', 'decayed')"""
        ).fetchall()
    desired = {str(r["id"]): dict(r) for r in rows}

    try:
        existing_ids = set(kernel._memory_index.list_memory_ids())
    except Exception as exc:
        logger.warning("Could not list memory index IDs after restore: %s", exc)
        existing_ids = set()
        persist_memory_index_repair(
            kernel._db,
            MEMORY_INDEX_RECONCILE_AGGREGATE,
            MEMORY_INDEX_RECONCILE_EVENT,
            0,
            f"list_memory_ids failed during restore: {exc}",
        )
        for mid in desired:
            persist_memory_index_repair(
                kernel._db, mid, "MemoryDerived", 0,
                f"list_memory_ids failed during restore: {exc}",
            )
        return False

    for mid in existing_ids - set(desired):
        try:
            kernel._memory_index.delete_memory(mid)
        except Exception as exc:
            persist_memory_index_repair(
                kernel._db, mid, "MemoryDeleted", 0, str(exc),
            )

    for mid, row in desired.items():
        content = str(row.get("content") or "")
        if not content:
            # An active-but-empty projection must not retain an older document
            # under the same Chroma ID.
            try:
                kernel._memory_index.delete_memory(mid)
            except Exception as exc:
                persist_memory_index_repair(
                    kernel._db, mid, "MemoryDeleted", 0, str(exc),
                )
            continue
        try:
            kernel._memory_index.index_memory(
                content=content,
                metadata={
                    "category": str(row.get("category") or "general"),
                    "source": str(row.get("source") or ""),
                },
                memory_id=mid,
            )
        except Exception as exc:
            persist_memory_index_repair(
                kernel._db, mid, "MemoryDerived", 0, str(exc),
            )
    return True


def _legacy_chat_bootstrap_event_rows(
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert legacy chat projections into synthetic event_log rows.

    Returns [] when the snapshot already has chat events. Synthetic rows use
    seq values continuing after the imported max so they can be imported in
    the same atomic transaction as the rest of the snapshot.
    """
    if any(r.get("type") in CHAT_EVENT_TYPES for r in event_rows):
        return []
    if not conversations and not messages:
        return []

    max_seq = max((int(r["seq"]) for r in event_rows), default=0)
    now = datetime.now(UTC).isoformat()
    out: list[dict[str, Any]] = []

    for conv in conversations:
        max_seq += 1
        out.append({
            "seq": max_seq,
            "id": f"evt_bootstrap_conv_{conv['id']}",
            "type": "ConversationCreated",
            "aggregate_type": "conversation",
            "aggregate_id": conv["id"],
            "actor": "import",
            "payload": {
                "title": conv.get("title", "New Conversation"),
                "summary": conv.get("summary"),
                "created_at": conv.get("created_at"),
            },
            "caused_by": None,
            "correlation_id": None,
            "ts": conv.get("created_at") or now,
        })

    for msg in messages:
        max_seq += 1
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None and isinstance(tool_calls, str):
            try:
                tool_calls = json.loads(tool_calls)
            except json.JSONDecodeError:
                pass
        out.append({
            "seq": max_seq,
            "id": f"evt_bootstrap_msg_{msg['id']}",
            "type": "MessageAppended",
            "aggregate_type": "conversation",
            "aggregate_id": msg["conversation_id"],
            "actor": "import",
            "payload": {
                "message_id": msg["id"],
                "role": msg["role"],
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
                "tool_call_id": msg.get("tool_call_id"),
                "created_at": msg.get("created_at"),
            },
            "caused_by": None,
            "correlation_id": None,
            "ts": msg.get("created_at") or now,
        })
    return out


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
    """Rebuild all registered aggregate types.

    After projection replay, run a full Chroma ↔ SQLite reconcile so callers
    that deferred rebuild via ``import_event_log_rows(..., rebuild_projections=False)``
    still purge orphan vectors that event replay alone would miss.
    """
    from .memory_index_sync import memory_index_operation_lock

    result = {}
    for at in list(projectors._OWNED_TABLES):
        result[at] = rebuild(kernel, at)
    with memory_index_operation_lock:
        _reconcile_memory_index_after_restore(kernel)
    return result

def iter_snapshot_json_chunks(kernel):
    """Yield UTF-8 chunks of a lossless snapshot JSON document.

    Streams ``event_log`` row-by-row so the HTTP layer need not hold the
    full serialized body. Wire format matches :meth:`snapshot`.

    Uses a dedicated connection (not the TLS pool) so a mid-stream client
    disconnect cannot leave a sticky ``BEGIN`` on a reused worker connection.
    """
    now = datetime.now(UTC).isoformat()
    snapshot_id = str(uuid.uuid4())
    conn = kernel._db.get_raw_connection()
    try:
        # Explicit BEGIN keeps all streamed batches and counts on one WAL
        # snapshot until the generator finishes or is closed.
        conn.execute("BEGIN")
        conn.execute("SELECT 1 FROM event_log LIMIT 1").fetchone()
        yield from iter_snapshot_document_bytes(
            conn,
            snapshot_id=snapshot_id,
            exported_at=now,
            export_format=EXPORT_FORMAT,
        )
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

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
    """Restore from event_log-based snapshot.

    Legacy chat projections (conversations/messages without chat events) are
    converted into synthetic event rows and imported in the same SQLite
    transaction as the rest of the snapshot — no post-commit bootstrap.
    """
    event_rows = list(snapshot.get("event_log", []))
    conversations = snapshot.get("conversations", [])
    messages = snapshot.get("messages", [])

    bootstrap_rows = _legacy_chat_bootstrap_event_rows(
        conversations, messages, event_rows,
    )
    all_rows = event_rows + bootstrap_rows

    imported_events = import_event_log_rows(
        kernel, all_rows, rebuild_projections=True,
    )

    return {
        "format": EXPORT_FORMAT,
        "events_imported": imported_events,
        "conversations_imported": sum(
            1 for r in bootstrap_rows if r["type"] == "ConversationCreated"
        ),
        "messages_imported": sum(
            1 for r in bootstrap_rows if r["type"] == "MessageAppended"
        ),
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


def prune_handler_executions(kernel, *, retention_days: int) -> int:
    """Soft-prune terminal handler_executions older than ``retention_days``.

    Kernel-space maintenance privilege (INV-S1a / ADR-R014) — same DML
    allowlist class as rebuild/erase. Does **not** delete ``event_log`` rows;
    a full rebuild can recreate projections until event compaction exists
    (Non-goal).
    """
    if retention_days <= 0:
        return 0
    from datetime import UTC, datetime, timedelta

    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    with kernel._db.get_db() as conn:
        cur = conn.execute(
            """DELETE FROM handler_executions
               WHERE status IN ('completed', 'failed')
                 AND completed_at != ''
                 AND completed_at < ?""",
            (cutoff,),
        )
        return int(cur.rowcount or 0)

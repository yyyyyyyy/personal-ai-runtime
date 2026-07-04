"""Kernel Sovereignty Mixin — export, import, and rebuild.

Extracted from kernel.py. Handles the data sovereignty lifecycle:
  - Lossless export of the Event Log
  - Import with idempotent seq/id preservation
  - Full projection rebuild from the Event Log
  - Incremental rebuild via projection checkpoints

All methods use Kernel ABI (emit_event / read_events) and respect
the Kernel Boundary.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import projectors
from .constants import (
    CHAT_EVENT_TYPES,
    MEMORY_INDEX_EVENT_TYPES,
    PROJECTION_SNAPSHOT_AGGREGATES,
)

EXPORT_FORMAT = "snapshot"


# All projection tables (derived from _OWNED_TABLES so rebuild / import stay in sync).
# Includes conversations, messages, and background_tasks which are owned by
# the conversation and background_task aggregates respectively.
def _all_projection_tables() -> set[str]:
    result: set[str] = set()
    for tables in projectors._OWNED_TABLES.values():
        result.update(tables)
    return result


class SovereigntyMixin:  # type: ignore[attr-defined]  # mixed into Kernel which provides _db/emit_event/read_events
    """Data sovereignty operations — export, import, rebuild.

    Mixed into Kernel. Uses self._db, self.emit_event, self.read_events,
    self._sync_memory_index, and projectors.
    """

    # ── Event Log guard helpers ──────────────────────────────────────────

    def _drop_event_log_guards(self, conn) -> None:
        conn.execute("DROP TRIGGER IF EXISTS event_log_no_update")
        conn.execute("DROP TRIGGER IF EXISTS event_log_no_delete")

    def _ensure_event_log_guards(self, conn) -> None:
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

    # ── Export / import ──────────────────────────────────────────────────

    def export_event_log_rows(self) -> list[dict[str, Any]]:
        """Export full event_log for lossless snapshot."""
        with self._db.get_db() as conn:
            rows = conn.execute("SELECT * FROM event_log ORDER BY seq ASC").fetchall()
        return [dict(r) for r in rows]

    def import_event_log_rows(
        self,
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
        with self._db.get_db() as conn:
            self._drop_event_log_guards(conn)
            for table in _all_projection_tables():
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
            self._ensure_event_log_guards(conn)

        if rebuild_projections:
            self.rebuild_all()
            for event in self.read_events(types=list(MEMORY_INDEX_EVENT_TYPES)):
                self._sync_memory_index(event)
        return len(rows)

    def table_counts(self, tables: tuple[str, ...]) -> dict[str, int]:
        """Kernel-space row counts for sovereignty verification."""
        out: dict[str, int] = {}
        with self._db.get_db() as conn:
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                out[table] = int(row["c"])
        return out

    def count_events(self, aggregate_type: str) -> int:
        """Count events in event_log filtered by aggregate_type (kernel-space)."""
        with self._db.get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM event_log WHERE aggregate_type = ?",
                (aggregate_type,),
            ).fetchone()
            return int(row["c"])

    # ── Chat snapshot bootstrap ──────────────────────────────────────────

    def bootstrap_chat_from_snapshot(
        self,
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
            self.emit_event(
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
            self.emit_event(
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

    def export_chat_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Export conversation/message projections (denormalized backup)."""
        with self._db.get_db() as conn:
            conversations = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM conversations ORDER BY created_at ASC"
                ).fetchall()
            ]
            messages = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM messages ORDER BY created_at ASC"
                ).fetchall()
            ]
        return conversations, messages

    # ── Rebuild ──────────────────────────────────────────────────────────

    def _checkpoint_seq(self, agent_id: str, aggregate_type: str) -> int:
        """Return the last_applied_seq for a per-agent checkpoint (0 if none)."""
        with self._db.get_db() as conn:
            row = conn.execute(
                "SELECT last_applied_seq FROM projection_checkpoints "
                "WHERE agent_id = ? AND aggregate_type = ?",
                (agent_id, aggregate_type),
            ).fetchone()
        return int(row["last_applied_seq"]) if row else 0

    def _restore_table_snapshot(self, conn, table: str, rows: list[dict[str, Any]]) -> None:
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
        self,
        aggregate_type: str,
        agent_id: str = "kernel",
    ) -> dict[str, Any]:
        """Persist projection tables + last_applied_seq for incremental rebuild.

        agent_id defaults to 'kernel' for global (non-agent) projections.
        Per-agent snapshots use the agent's instance id.
        """
        from datetime import UTC, datetime

        tables = projectors.owned_tables(aggregate_type)
        events = self.read_events(aggregate_type=aggregate_type)
        last_seq = max((int(e.seq) for e in events if e.seq is not None), default=0)

        snapshot: dict[str, list[dict[str, Any]]] = {}
        with self._db.get_db() as conn:
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
        self,
        aggregate_types: tuple[str, ...] | list[str] | None = None,
        agent_id: str = "kernel",
    ) -> list[dict[str, Any]]:
        """Persist checkpoints for one or more aggregates."""
        types = aggregate_types or PROJECTION_SNAPSHOT_AGGREGATES
        return [self.save_projection_snapshot(agg, agent_id=agent_id) for agg in types]

    def rebuild(
        self,
        aggregate_type: str,
        agent_id: str = "kernel",
    ) -> int:
        """Rebuild projection from Event Log (incremental when checkpoint exists).

        agent_id defaults to 'kernel' for global projections.
        Per-agent rebuilds restore agent-specific state from the checkpoint.
        """
        tables = projectors.owned_tables(aggregate_type)
        events = self.read_events(aggregate_type=aggregate_type)
        with self._db.get_db() as conn:
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
                    self._restore_table_snapshot(conn, table, snapshot.get(table, []))

            replayed = 0
            for event in events:
                if event.seq is not None and int(event.seq) <= last_seq:
                    continue
                projectors.apply(event, conn)
                replayed += 1

        for event in events:
            if checkpoint and event.seq is not None and int(event.seq) <= last_seq:
                continue
            self._sync_memory_index(event)
        return replayed if checkpoint else len(events)

    def rebuild_all(self) -> dict[str, int]:
        """Rebuild all registered aggregate types."""
        result = {}
        for at in list(projectors._OWNED_TABLES):
            result[at] = self.rebuild(at)
        return result

    # ── Sovereignty operations (ex-DigitalLegacy, now kernel first-class) ─

    def snapshot(self) -> dict[str, Any]:
        """Export complete personal snapshot: event_log + conversations + messages.

        This is the kernel-space equivalent of DigitalLegacy.export_all().
        It assembles the snapshot dict from existing sovereignty primitives
        (export_event_log_rows, export_chat_rows, table_counts) plus a
        projection checkpoint save.
        """
        now = datetime.now(UTC).isoformat()
        snapshot_id = str(uuid.uuid4())

        event_log = self.export_event_log_rows()
        conversations, messages = self.export_chat_rows()

        snapshot: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "exported_at": now,
            "format": EXPORT_FORMAT,
            "event_log": event_log,
            "conversations": conversations,
            "messages": messages,
            "counts": {
                "event_log": len(event_log),
                "conversations": len(conversations),
                "messages": len(messages),
                "goals": self.table_counts(("goals",)).get("goals", 0),
                "memories": self.table_counts(("memories",)).get("memories", 0),
                "notifications": self.table_counts(("notifications",)).get(
                    "notifications", 0
                ),
            },
        }

        self.save_projection_snapshots()
        return snapshot

    def restore(self, snapshot: dict, read_only: bool = True) -> dict[str, Any]:
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
            return self._restore_from_snapshot(snapshot)
        return self._import_legacy_goals_memories(snapshot)

    def _restore_from_snapshot(self, snapshot: dict) -> dict:
        """Restore from event_log-based snapshot."""
        event_rows = snapshot.get("event_log", [])
        conversations = snapshot.get("conversations", [])
        messages = snapshot.get("messages", [])

        imported_events = self.import_event_log_rows(
            event_rows, rebuild_projections=True
        )

        chat_bootstrapped = self.bootstrap_chat_from_snapshot(
            conversations, messages, event_rows
        )

        return {
            "format": EXPORT_FORMAT,
            "events_imported": imported_events,
            "conversations_imported": chat_bootstrapped.get("conversations", 0),
            "messages_imported": chat_bootstrapped.get("messages", 0),
        }

    def _import_legacy_goals_memories(self, snapshot: dict) -> dict[str, Any]:
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
            self.emit_event(
                "GoalCreated",
                "goal",
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

    def erase(self) -> dict:
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

        Database._instance = None  # type: ignore[attr-defined]
        database_module.db = Database()

        return {
            "status": "destroyed",
            "message": "All local data removed. Restart the server to reinitialize.",
        }

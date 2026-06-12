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
from typing import Any

from . import projectors
from .constants import (
    CHAT_EVENT_TYPES,
    MEMORY_INDEX_EVENT_TYPES,
    PROJECTION_SNAPSHOT_AGGREGATES,
    PROJECTION_TABLES,
)


class SovereigntyMixin:
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
        """Bulk-import events preserving seq/id; optionally rebuild all projections."""
        with self._db.get_db() as conn:
            self._drop_event_log_guards(conn)
            for table in PROJECTION_TABLES:
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

    def save_projection_snapshot(self, aggregate_type: str) -> dict[str, Any]:
        """Persist projection tables + last_applied_seq for incremental rebuild."""
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
                   (aggregate_type, last_applied_seq, snapshot_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    aggregate_type,
                    last_seq,
                    json.dumps(snapshot),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return {"aggregate_type": aggregate_type, "last_applied_seq": last_seq}

    def save_projection_snapshots(
        self,
        aggregate_types: tuple[str, ...] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Persist checkpoints for one or more aggregates."""
        types = aggregate_types or PROJECTION_SNAPSHOT_AGGREGATES
        return [self.save_projection_snapshot(agg) for agg in types]

    def rebuild(self, aggregate_type: str) -> int:
        """Rebuild projection from Event Log (incremental when checkpoint exists)."""
        tables = projectors.owned_tables(aggregate_type)
        events = self.read_events(aggregate_type=aggregate_type)
        with self._db.get_db() as conn:
            checkpoint = conn.execute(
                "SELECT last_applied_seq, snapshot_json FROM projection_checkpoints WHERE aggregate_type = ?",
                (aggregate_type,),
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

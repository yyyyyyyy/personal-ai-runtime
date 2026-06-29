"""Digital Legacy — lossless export/import of personal Event Log + chat data."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

from app.config import settings
from app.core.runtime.kernel_instance import kernel as default_kernel
from app.store import database as database_module
from app.store.database import db as default_db

EXPORT_FORMAT = "snapshot"


class LegacyImportResult(TypedDict):
    format: str
    profile_categories: int
    goals_imported: int
    memories_imported: int


class DigitalLegacy:
    """Manages persona export, import, and destruction for data sovereignty."""

    def __init__(self, *, kernel=None, db=None):
        self._kernel = kernel or default_kernel
        self._db = db or default_db

    def export_persona(self) -> dict:
        return self.export_all()

    def export_all(self) -> dict:
        """Export complete personal snapshot: event_log + conversations + messages."""
        now = datetime.now(UTC).isoformat()
        snapshot_id = str(uuid.uuid4())

        event_log = self._kernel.export_event_log_rows()
        conversations, messages = self._kernel.export_chat_rows()

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
                "goals": self._kernel.table_counts(("goals",)).get("goals", 0),
                "memories": self._kernel.table_counts(("memories",)).get("memories", 0),
                "notifications": self._kernel.table_counts(("notifications",)).get(
                    "notifications", 0
                ),
                "schedules": self._kernel.table_counts(("schedules",)).get("schedules", 0),
            },
        }

        with self._db.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES ('persona_export', ?)",
                (json.dumps({"snapshot_id": snapshot_id, "format": EXPORT_FORMAT}),),
            )

        self._kernel.save_projection_snapshots()

        return snapshot

    def import_persona(self, snapshot: dict, read_only: bool = True) -> dict:
        return self.import_all(snapshot, read_only=read_only)

    def import_all(self, snapshot: dict, read_only: bool = True) -> dict[str, Any]:
        """Import snapshot. Write import requires read_only=False."""
        if read_only:
            return self._validate_snapshot(snapshot)

        export_format = snapshot.get("format")
        if export_format == EXPORT_FORMAT:
            return self._import_snapshot(snapshot)
        if snapshot.get("event_log") is not None:
            return self._import_snapshot(snapshot)
        return cast(dict[str, Any], self._import_legacy_goals_memories(snapshot))

    def _validate_snapshot(self, snapshot: dict) -> dict:
        """Dry-run validation without writing."""
        event_log = snapshot.get("event_log", [])
        return {
            "valid": True,
            "format": snapshot.get("format"),
            "counts": {
                "event_log": len(event_log),
                "conversations": len(snapshot.get("conversations", [])),
                "messages": len(snapshot.get("messages", [])),
            },
        }

    def _import_snapshot(self, snapshot: dict) -> dict:
        event_rows = snapshot.get("event_log", [])
        conversations = snapshot.get("conversations", [])
        messages = snapshot.get("messages", [])

        imported_events = self._kernel.import_event_log_rows(
            event_rows, rebuild_projections=True
        )

        chat_bootstrapped = self._kernel.bootstrap_chat_from_snapshot(
            conversations, messages, event_rows
        )

        return {
            "format": EXPORT_FORMAT,
            "events_imported": imported_events,
            "conversations_imported": chat_bootstrapped.get("conversations", 0),
            "messages_imported": chat_bootstrapped.get("messages", 0),
        }

    def _import_legacy_goals_memories(self, snapshot: dict) -> LegacyImportResult:
        """Best-effort import for older lossy snapshots (goals/memories only)."""
        from app.core.agents.memory_engine import memory_engine
        from app.core.agents.user_profile import user_profile

        imported: LegacyImportResult = {
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
                imported["profile_categories"] += 1

        for goal in snapshot.get("goals", []):
            gid = goal.get("id") or str(uuid.uuid4())
            self._kernel.emit_event(
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
            imported["goals_imported"] += 1

        for mem in snapshot.get("memories", []):
            memory_engine.store_memory(
                mem.get("content", ""),
                category=mem.get("category", "fact"),
                source="legacy_import",
                confidence=float(mem.get("confidence", 0.5)),
                actor="import",
            )
            imported["memories_imported"] += 1

        return imported

    def destroy_all(self) -> dict:
        """Remove database and vector store files (irreversible)."""
        db_path = Path(settings.sqlite_path)
        vector_path = Path(settings.vector_dir)

        if db_path.exists():
            db_path.unlink()
        if vector_path.exists():
            shutil.rmtree(vector_path, ignore_errors=True)

        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.vector_dir).mkdir(parents=True, exist_ok=True)

        from app.store.database import Database

        Database._instance = None  # type: ignore[attr-defined]
        database_module.db = Database()

        return {
            "status": "destroyed",
            "message": "All local data removed. Restart the server to reinitialize.",
        }

    def export_to_file(self, filepath: str) -> str:
        snapshot = self.export_all()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return filepath

    def import_from_file(self, filepath: str, read_only: bool = True) -> dict:
        with open(filepath, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        return self.import_all(snapshot, read_only=read_only)

    def snapshot_counts(self) -> dict[str, int]:
        """Current instance counts for roundtrip verification."""
        return self._kernel.table_counts(
            (
                "event_log",
                "conversations",
                "messages",
                "goals",
                "memories",
                "notifications",
                "schedules",
            )
        )


digital_legacy = DigitalLegacy()

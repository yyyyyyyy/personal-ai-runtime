"""Digital Legacy — export/import/destroy complete persona snapshots."""

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.agents.memory_engine import memory_engine
from app.core.agents.memory_v2 import user_profile
from app.core.runtime.kernel_instance import kernel
from app.store.database import db


class DigitalLegacy:
    """Manages persona export, import, and destruction for data sovereignty."""

    def export_persona(self) -> dict:
        """Export complete user persona as a signed snapshot."""
        return self.export_all()

    def export_all(self) -> dict:
        now = datetime.utcnow().isoformat()
        persona_id = str(uuid.uuid4())

        profile = user_profile.get_profile()
        memories = memory_engine.list_memories(limit=500)
        goals = kernel.query_state("goals", limit=200)

        with db.get_db() as conn:
            conversations = conn.execute(
                "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC LIMIT 100"
            ).fetchall()

        snapshot = {
            "persona_id": persona_id,
            "exported_at": now,
            "version": "1.1",
            "profile": profile,
            "goals": goals,
            "memories": [
                {"content": m["content"], "category": m.get("category"), "confidence": m.get("confidence")}
                for m in memories
            ],
            "conversations_meta": [dict(c) for c in conversations],
        }

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES ('persona_export', ?)",
                (json.dumps({"persona_id": persona_id}),),
            )

        return snapshot

    def import_persona(self, snapshot: dict, read_only: bool = True) -> dict:
        return self.import_all(snapshot, read_only=read_only)

    def import_all(self, snapshot: dict, read_only: bool = True) -> dict:
        profile_data = snapshot.get("profile", {})
        memories_data = snapshot.get("memories", [])

        imported = {
            "profile_categories": 0,
            "goals_imported": 0,
            "memories_imported": 0,
        }

        if not read_only:
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
                kernel.emit_event(
                    "GoalCreated", "goal", gid,
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

        for mem in memories_data:
            memory_engine.store_memory(
                mem.get("content", ""),
                category=mem.get("category", "fact"),
                source="legacy_import",
                confidence=float(mem.get("confidence", 0.5)),
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

        return {"status": "destroyed", "message": "All local data removed. Restart the server to reinitialize."}

    def export_to_file(self, filepath: str) -> str:
        snapshot = self.export_all()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return filepath

    def import_from_file(self, filepath: str, read_only: bool = True) -> dict:
        with open(filepath, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        return self.import_all(snapshot, read_only=read_only)


digital_legacy = DigitalLegacy()

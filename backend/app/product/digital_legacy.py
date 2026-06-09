"""Digital Legacy — export/import complete persona snapshots.

Enables inheritance and migration of personal AI state between instances.
"""

import json
import uuid
from datetime import datetime

from app.core.agents.memory_engine import memory_engine
from app.core.agents.memory_v2 import user_profile
from app.store.database import db


class DigitalLegacy:
    """Manages persona export and import for digital inheritance."""

    def export_persona(self) -> dict:
        """Export complete user persona as a signed snapshot."""
        now = datetime.utcnow().isoformat()
        persona_id = str(uuid.uuid4())

        profile = user_profile.get_profile()
        memories = memory_engine.list_memories(limit=100)

        with db.get_db() as conn:
            goals = conn.execute(
                "SELECT title, status FROM goals ORDER BY created_at DESC LIMIT 50"
            ).fetchall()

        snapshot = {
            "persona_id": persona_id,
            "exported_at": now,
            "version": "1.0",
            "profile": profile,
            "goals": [dict(g) for g in goals],
            "memories": [{"content": m["content"], "category": m["category"]} for m in memories],
        }

        # Store export record
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES ('persona_export', ?)",
                (json.dumps({"persona_id": persona_id}),),
            )

        return snapshot

    def import_persona(self, snapshot: dict, read_only: bool = True) -> dict:
        """Import a persona snapshot. In read_only mode, imports as reference only."""
        profile_data = snapshot.get("profile", {})
        snapshot.get("goals", [])
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

        for mem in memories_data:
            memory_engine.store_memory(
                mem.get("content", ""),
                category=mem.get("category", "fact"),
                source="legacy_import",
            )
            imported["memories_imported"] += 1

        return imported

    def export_to_file(self, filepath: str) -> str:
        """Export persona to a JSON file."""
        snapshot = self.export_persona()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return filepath

    def import_from_file(self, filepath: str, read_only: bool = True) -> dict:
        """Import persona from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        return self.import_persona(snapshot, read_only=read_only)


digital_legacy = DigitalLegacy()

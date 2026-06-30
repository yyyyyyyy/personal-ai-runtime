"""Structured user profile with confidence scoring, time decay, and conflict resolution."""

import json
from datetime import UTC, datetime, timedelta

from app.store.database import db

CATEGORIES = ["preferences", "values", "relationships", "health", "finance", "career"]


class UserProfile:
    """Structured user profile with confidence scoring and time decay."""

    def update_profile(self, category: str, data: dict, confidence: float = 0.5):
        """Update a profile category with merge conflict resolution."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")

        now = datetime.now(UTC).isoformat()
        existing = self._get_category(category)

        if existing:
            existing_data = json.loads(existing["data_json"])
            existing_confidence = existing["confidence"]

            updated_at = datetime.fromisoformat(existing["updated_at"]) if existing.get("updated_at") else datetime.now(UTC)
            if (datetime.now(UTC) - updated_at) > timedelta(days=30):
                existing_confidence *= 0.5

            merged = {}
            all_keys = set(existing_data.keys()) | set(data.keys())
            for key in all_keys:
                if key not in data:
                    merged[key] = existing_data[key]
                elif key not in existing_data:
                    merged[key] = data[key]
                else:
                    merged[key] = data[key] if confidence > existing_confidence else existing_data[key]

            new_confidence = max(confidence, existing_confidence)
            with db.get_db() as conn:
                conn.execute(
                    "UPDATE user_profile SET data_json = ?, confidence = ?, updated_at = ? WHERE category = ?",
                    (json.dumps(merged), new_confidence, now, category),
                )
        else:
            with db.get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO user_profile (id, category, data_json, confidence, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (category, category, json.dumps(data), confidence, now),
                )

    def get_profile(self) -> dict:
        """Get the full user profile across all categories."""
        profile = {}
        for category in CATEGORIES:
            data = self._get_category(category)
            if data:
                profile[category] = {
                    "data": json.loads(data["data_json"]),
                    "confidence": data["confidence"],
                }
        return profile

    def get_category(self, category: str) -> dict | None:
        """Get a single profile category."""
        return self._get_category(category)

    def _get_category(self, category: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM user_profile WHERE category = ?", (category,)
            ).fetchone()
        return dict(row) if row else None

    def refresh_all(self):
        """Recalculate time decay on all categories."""
        now = datetime.now(UTC)
        for category in CATEGORIES:
            existing = self._get_category(category)
            if existing:
                updated = datetime.fromisoformat(existing["updated_at"])
                if (now - updated) > timedelta(days=30):
                    new_conf = existing["confidence"] * 0.5
                    with db.get_db() as conn:
                        conn.execute(
                            "UPDATE user_profile SET confidence = ? WHERE category = ?",
                            (new_conf, category),
                        )


user_profile = UserProfile()

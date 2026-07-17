"""Structured user profile with confidence scoring, time decay, and conflict resolution.

User profile writes go through Kernel events (UserProfileUpdated) so changes
are recorded in the event_log and remain auditable. The `user_profile` table is
APP_STORAGE — not a core governance projection — but the write path is unified
through the Kernel.

Boundary vs Memory:
- UserProfile = structured category bags (preferences / values / …) for settings-like facts.
- MemoryDerived (via MemoryExtractor) = free-form conversational facts for recall.
Do not write free-form chat extracts into UserProfile.
"""

import json
from datetime import UTC, datetime, timedelta

from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel

CATEGORIES = ["preferences", "values", "relationships", "health", "finance", "career"]


class UserProfile:
    """Structured user profile with confidence scoring and time decay."""

    def update_profile(self, category: str, data: dict, confidence: float = 0.5):
        """Update a profile category with merge conflict resolution."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")

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
        else:
            merged = data
            new_confidence = confidence

        kernel.emit_event(
            "UserProfileUpdated",
            "user_profile",
            category,
            payload={
                "category": category,
                "data_json": json.dumps(merged),
                "confidence": new_confidence,
            },
            actor="system",
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
        return read_ports.query_user_profile_category(category)

    def refresh_all(self):
        """Recalculate time decay on all categories."""
        for category in CATEGORIES:
            existing = self._get_category(category)
            if existing:
                updated = datetime.fromisoformat(existing["updated_at"])
                if (datetime.now(UTC) - updated) > timedelta(days=30):
                    new_conf = existing["confidence"] * 0.5
                    kernel.emit_event(
                        "UserProfileUpdated",
                        "user_profile",
                        category,
                        payload={
                            "category": category,
                            "data_json": existing["data_json"],
                            "confidence": new_conf,
                        },
                        actor="system",
                    )


user_profile = UserProfile()

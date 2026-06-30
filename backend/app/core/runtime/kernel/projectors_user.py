"""Projectors for user profile — event-sourced write path for user_profile table."""

from .event import Event
from .projectors_registry import projector


@projector("UserProfileUpdated")
def _on_user_profile_updated(event: Event, conn) -> None:
    p = event.payload
    category = p["category"]
    conn.execute(
        """INSERT OR REPLACE INTO user_profile
           (id, category, data_json, confidence, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (category, category, p["data_json"], p["confidence"], event.ts),
    )

"""Notification generation utilities."""

import uuid
from datetime import UTC, datetime

from app.store import database


def find_notification(notif_type: str, title: str) -> dict | None:
    """Return an existing notification with the same type and title, if any."""
    with database.db.get_db() as conn:
        row = conn.execute(
            "SELECT id, type, title, content, created_at FROM notifications "
            "WHERE type = ? AND title = ? LIMIT 1",
            (notif_type, title),
        ).fetchone()
    return dict(row) if row else None


def _embed_related_id(content: str, related_id: str | None) -> str:
    if related_id:
        return f"@related:{related_id}\n{content}"
    return content


def parse_related_id(content: str) -> tuple[str | None, str]:
    """Extract optional related entity id prefix from notification content."""
    if content.startswith("@related:"):
        first_line, _, rest = content.partition("\n")
        return first_line.removeprefix("@related:"), rest
    return None, content


def create_notification(
    notif_type: str,
    title: str,
    content: str,
    *,
    related_id: str | None = None,
) -> dict:
    """Create a notification and return it (idempotent by type + title)."""
    existing = find_notification(notif_type, title)
    if existing:
        return existing

    stored_content = _embed_related_id(content, related_id)
    nid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with database.db.get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, type, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (nid, notif_type, title, stored_content, now),
        )
    return {
        "id": nid,
        "type": notif_type,
        "title": title,
        "content": stored_content,
        "created_at": now,
    }

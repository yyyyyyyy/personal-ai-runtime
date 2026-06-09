"""Notification generation utilities."""

import uuid
from datetime import datetime

from app.store.database import db


def create_notification(notif_type: str, title: str, content: str) -> dict:
    """Create a notification and return it."""
    nid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, type, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (nid, notif_type, title, content, now),
        )
    return {"id": nid, "type": notif_type, "title": title, "content": content, "created_at": now}

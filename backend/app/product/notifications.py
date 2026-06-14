"""Notification generation utilities."""

import re
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


def find_review_id_for_notification_title(title: str) -> str | None:
    """Match a review record id from a notification title."""
    with database.db.get_db() as conn:
        daily = re.match(r"^每日复盘 - (\d{4}-\d{2}-\d{2})$", title)
        if daily:
            row = conn.execute(
                "SELECT id FROM reviews WHERE type = 'daily' AND period_start = ? LIMIT 1",
                (daily.group(1),),
            ).fetchone()
            return row["id"] if row else None

        weekly = re.match(r"^每周复盘 - (.+?) ~ (.+)$", title)
        if weekly:
            row = conn.execute(
                "SELECT id FROM reviews WHERE type = 'weekly' AND period_start = ? AND period_end = ? LIMIT 1",
                (weekly.group(1), weekly.group(2)),
            ).fetchone()
            return row["id"] if row else None

        monthly = re.match(r"^每月复盘 - (.+?) ~ (.+)$", title)
        if monthly:
            row = conn.execute(
                "SELECT id FROM reviews WHERE type = 'monthly' AND period_start = ? AND period_end = ? LIMIT 1",
                (monthly.group(1), monthly.group(2)),
            ).fetchone()
            return row["id"] if row else None
    return None


def ensure_related_id_on_notification(row: dict) -> dict:
    """Backfill @related: prefix on review notifications when missing."""
    if row.get("type") != "review" or row.get("content", "").startswith("@related:"):
        return row

    related_id = find_review_id_for_notification_title(row.get("title", ""))
    if not related_id:
        return row

    _, body = parse_related_id(row["content"])
    updated = _embed_related_id(body, related_id)
    with database.db.get_db() as conn:
        conn.execute(
            "UPDATE notifications SET content = ? WHERE id = ?",
            (updated, row["id"]),
        )
    return {**row, "content": updated}


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
        if related_id and not existing["content"].startswith("@related:"):
            _, body = parse_related_id(existing["content"])
            updated = _embed_related_id(body, related_id)
            with database.db.get_db() as conn:
                conn.execute(
                    "UPDATE notifications SET content = ? WHERE id = ?",
                    (updated, existing["id"]),
                )
            existing = {**existing, "content": updated}
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

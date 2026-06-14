"""Tests for notification related-id backfill."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.product.notifications import (
    create_notification,
    ensure_related_id_on_notification,
    find_review_id_for_notification_title,
    parse_related_id,
)
from app.store.database import Database


@pytest.fixture
def notif_db(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "notifications.db"))
    monkeypatch.setattr("app.product.notifications.database.db", db)
    monkeypatch.setattr("app.store.database.db", db)
    return db


def test_parse_related_id():
    rid, body = parse_related_id("@related:abc-123\nHello")
    assert rid == "abc-123"
    assert body == "Hello"


def test_create_notification_updates_existing_with_related_id(notif_db):
    first = create_notification("review", "每日复盘 - 2026-06-14", "old content")
    assert first["content"] == "old content"

    second = create_notification(
        "review",
        "每日复盘 - 2026-06-14",
        "new content",
        related_id="rev-001",
    )
    assert second["id"] == first["id"]
    assert second["content"].startswith("@related:rev-001\n")


def test_ensure_related_id_backfill_from_review_title(notif_db):
    with notif_db.get_db() as conn:
        conn.execute(
            "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev-weekly-1", "weekly", "2026-06-07", "2026-06-14", "body", "{}", "2026-06-14T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO notifications (id, type, title, content, read, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "n1",
                "review",
                "每周复盘 - 2026-06-07 ~ 2026-06-14",
                "snapshot content",
                1,
                "2026-06-14T00:00:00Z",
            ),
        )

    row = {
        "id": "n1",
        "type": "review",
        "title": "每周复盘 - 2026-06-07 ~ 2026-06-14",
        "content": "snapshot content",
        "read": 1,
        "created_at": "2026-06-14T00:00:00Z",
    }
    updated = ensure_related_id_on_notification(row)
    assert updated["content"].startswith("@related:rev-weekly-1\n")
    assert find_review_id_for_notification_title(row["title"]) == "rev-weekly-1"

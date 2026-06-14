"""Tests for notification related-id backfill and event-sourced writes."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.product.notifications import (
    create_notification,
    ensure_related_id_on_notification,
    find_review_id_for_notification_title,
    parse_related_id,
)
from app.store.database import Database


@pytest.fixture
def notif_env(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "notifications.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.product.notifications.default_kernel", k, raising=False)
    return db, k


def test_parse_related_id():
    rid, body = parse_related_id("@related:abc-123\nHello")
    assert rid == "abc-123"
    assert body == "Hello"


def test_create_notification_updates_existing_with_related_id(notif_env):
    db, k = notif_env
    first = create_notification("review", "每日复盘 - 2026-06-14", "old content", kernel=k)
    assert first["content"] == "old content"

    second = create_notification(
        "review",
        "每日复盘 - 2026-06-14",
        "new content",
        related_id="rev-001",
        kernel=k,
    )
    assert second["id"] == first["id"]
    assert second["content"].startswith("@related:rev-001\n")


def test_ensure_related_id_backfill_from_review_title(notif_env):
    db, k = notif_env
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev-weekly-1", "weekly", "2026-06-07", "2026-06-14", "body", "{}", "2026-06-14T00:00:00Z"),
        )

    k.emit_event(
        "NotificationCreated",
        "notification",
        "n1",
        payload={
            "type": "review",
            "title": "每周复盘 - 2026-06-07 ~ 2026-06-14",
            "content": "snapshot content",
            "created_at": "2026-06-14T00:00:00Z",
        },
        actor="test",
    )

    row = {
        "id": "n1",
        "type": "review",
        "title": "每周复盘 - 2026-06-07 ~ 2026-06-14",
        "content": "snapshot content",
        "read": 0,
        "created_at": "2026-06-14T00:00:00Z",
    }
    updated = ensure_related_id_on_notification(row, kernel=k)
    expected_id = find_review_id_for_notification_title(row["title"])
    assert expected_id
    assert updated["content"].startswith(f"@related:{expected_id}\n")


def test_notification_rebuild(notif_env):
    db, k = notif_env
    create_notification("alert", "Test alert", "Body", kernel=k)
    before = k.query_state("notifications")
    k.rebuild("notification")
    after = k.query_state("notifications")
    assert before == after
    assert len(after) == 1
    assert after[0]["read"] == 0

    k.emit_event("NotificationRead", "notification", after[0]["id"], payload={}, actor="test")
    k.rebuild("notification")
    read_rows = k.query_state("notifications")
    assert read_rows[0]["read"] == 1

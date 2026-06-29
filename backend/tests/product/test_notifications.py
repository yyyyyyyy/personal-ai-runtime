"""Tests for notification related-id handling and event-sourced writes."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.product.notifications import (  # noqa: E402
    create_notification,
    parse_related_id,
)
from app.core.runtime.kernel import Kernel  # noqa: E402
from app.store.database import Database  # noqa: E402


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
    first = create_notification("alert", "提醒 A", "old content", kernel=k)
    assert first["content"] == "old content"

    second = create_notification(
        "alert",
        "提醒 A",
        "new content",
        related_id="entity-001",
        kernel=k,
    )
    assert second["id"] == first["id"]
    assert second["content"].startswith("@related:entity-001\n")


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

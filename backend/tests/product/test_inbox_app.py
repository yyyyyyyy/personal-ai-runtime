"""Tests for proactive inbox app."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.product.inbox import generate_inbox_digest, poll_inbox
from app.store.database import Database


@pytest.fixture
def inbox_db(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "inbox.db"))
    monkeypatch.setattr("app.product.inbox.db", db)
    monkeypatch.setattr("app.store.database.db", db)
    monkeypatch.setattr("app.core.telemetry.event_recorder.db", db)
    return db


@pytest.mark.asyncio
async def test_poll_inbox_syncs_read_status(inbox_db):
    sample_unread = {
        "count": 1,
        "emails": [
            {
                "message_id": "msg-unread",
                "from": "a@b.com",
                "subject": "Still unread",
                "preview": "x",
                "date": "2026-06-10",
            },
        ],
    }

    with inbox_db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance, reason, status)
               VALUES ('msg-read', 'b@c.com', 'Read mail', 'y', datetime('now'), 'actionable', 0.5, 't', 'pending'),
                      ('msg-unread', 'a@b.com', 'Unread', 'x', datetime('now'), 'actionable', 0.5, 't', 'pending')"""
        )

    async def fake_invoke(name, args=None, actor="system", **kwargs):
        return {"status": "success", "result": json.dumps(sample_unread)}

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
            result = await poll_inbox(limit=10)

    assert result["synced_read"] == 1
    with inbox_db.get_db() as conn:
        rows = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM inbox_emails").fetchall()}
    assert rows["msg-read"] == "read"
    assert rows["msg-unread"] == "pending"


@pytest.mark.asyncio
async def test_poll_inbox_dedupes_and_notifies_important(inbox_db):
    sample = {
      "count": 2,
      "emails": [
          {
              "message_id": "msg-1",
              "from": "boss@corp.com",
              "subject": "Urgent",
              "preview": "Please review",
              "date": "2026-06-10",
          },
          {
              "message_id": "msg-2",
              "from": "news@shop.com",
              "subject": "Sale",
              "preview": "50% off",
              "date": "2026-06-10",
          },
      ],
  }

    async def fake_invoke(name, args=None, actor="system", **kwargs):
        assert name == "check_inbox"
        return {"status": "success", "result": json.dumps(sample)}

    classified = [
        {"message_id": "msg-1", "category": "important", "importance": 0.9, "reason": "老板"},
        {"message_id": "msg-2", "category": "ignorable", "importance": 0.1, "reason": "营销"},
    ]

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
            with patch("app.core.runtime.notification_bridge.push_notification") as push:
                result = await poll_inbox(limit=10)

    assert result["status"] == "ok"
    assert result["new_count"] == 2
    assert result["notified"] == 1
    push.assert_called_once()

    with inbox_db.get_db() as conn:
        rows = conn.execute("SELECT id FROM inbox_emails").fetchall()
        assert len(rows) == 2
        events = conn.execute(
            "SELECT type FROM events WHERE type = 'email_received'"
        ).fetchall()
        assert len(events) == 2

    # Second poll should skip duplicates
    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
            result2 = await poll_inbox(limit=10)
    assert result2["new_count"] == 0


def test_digest_idempotent(inbox_db):
    with inbox_db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance, reason)
               VALUES ('m1', 'a@b.com', 'Test', 'preview', datetime('now'), 'actionable', 0.5, 'test')"""
        )

    from app.product.notifications import create_notification

    with patch(
        "app.core.runtime.notification_bridge.push_notification",
        side_effect=lambda t, title, content: create_notification(t, title, content),
    ) as push:
        first = generate_inbox_digest()
        second = generate_inbox_digest()

    assert first is not None
    assert second is not None
    assert first["id"] == second["id"]
    push.assert_called_once()

"""Tests for proactive inbox app."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.product.inbox import generate_inbox_digest, poll_inbox, apply_inbox_poll_payload
from app.store.database import Database


@pytest.fixture
def inbox_db(tmp_path, monkeypatch):
    from app.core.runtime.kernel import Kernel

    db = Database(db_path=str(tmp_path / "inbox.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.product.inbox.kernel", k)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.product.inbox.db", db)
    monkeypatch.setattr("app.store.database.db", db)
    return db, k


@pytest.mark.asyncio
async def test_poll_inbox_syncs_read_status(inbox_db):
    db, k = inbox_db
    sample_unread = {
        "count": 1,
        "unread_only": True,
        "all_unread_message_ids": ["msg-unread"],
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

    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance, reason, status)
               VALUES ('msg-read', 'b@c.com', 'Read mail', 'y', datetime('now'), 'actionable', 0.5, 't', 'pending'),
                      ('msg-unread', 'a@b.com', 'Unread', 'x', datetime('now'), 'actionable', 0.5, 't', 'pending')"""
        )

    async def fake_invoke(name, args=None, actor="system", **kwargs):
        return {"status": "success", "result": json.dumps(sample_unread)}

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox.kernel._handler_execution_exists", return_value=True):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
                result = await poll_inbox(limit=10, execution_id="wi_inbox_test")

    assert result["synced_read"] == 1
    with db.get_db() as conn:
        rows = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM inbox_emails").fetchall()}
    assert rows["msg-read"] == "read"
    assert rows["msg-unread"] == "pending"


@pytest.mark.asyncio
async def test_poll_does_not_mark_read_when_unread_beyond_email_limit(inbox_db):
    """Pending mail still UNSEEN on IMAP must not be marked read when absent from truncated emails list."""
    db, _k = inbox_db
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance, reason, status)
               VALUES ('msg-old-unread', 'old@b.com', 'Older unread', 'y', datetime('now'),
                       'actionable', 0.5, 't', 'pending')"""
        )

    payload = {
        "count": 1,
        "unread_only": True,
        "all_unread_message_ids": ["msg-new", "msg-old-unread"],
        "emails": [
            {
                "message_id": "msg-new",
                "from": "new@b.com",
                "subject": "Newest only in batch",
                "preview": "x",
                "date": "2026-06-18",
            },
        ],
    }

    with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
        result = await apply_inbox_poll_payload(payload, execution_id="wi_inbox_test")

    assert result["synced_read"] == 0
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT status FROM inbox_emails WHERE id = 'msg-old-unread'"
        ).fetchone()
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_marks_read_when_absent_from_full_unread_set(inbox_db):
    db, _k = inbox_db
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance, reason, status)
               VALUES ('msg-read-elsewhere', 'b@c.com', 'Read mail', 'y', datetime('now'),
                       'actionable', 0.5, 't', 'pending')"""
        )

    payload = {
        "count": 0,
        "unread_only": True,
        "all_unread_message_ids": [],
        "emails": [],
    }

    with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
        result = await apply_inbox_poll_payload(payload, execution_id="wi_inbox_test")

    assert result["synced_read"] == 1
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT status FROM inbox_emails WHERE id = 'msg-read-elsewhere'"
        ).fetchone()
    assert row["status"] == "read"


@pytest.mark.asyncio
async def test_poll_inbox_dedupes_and_notifies_important(inbox_db):
    db, k = inbox_db
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
        with patch("app.product.inbox.kernel._handler_execution_exists", return_value=True):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
                with patch("app.core.runtime.notification_bridge.push_notification") as push:
                    result = await poll_inbox(limit=10, execution_id="wi_inbox_test")

    assert result["status"] == "ok"
    assert result["new_count"] == 2
    assert result["notified"] == 1
    push.assert_called_once()

    with db.get_db() as conn:
        rows = conn.execute("SELECT id FROM inbox_emails").fetchall()
        assert len(rows) == 2

    # C1: verify InboxEmailRecorded events in event_log (not legacy events table)
    with db.get_db() as conn:
        event_log_rows = conn.execute(
            "SELECT type FROM event_log WHERE type = 'InboxEmailRecorded'"
        ).fetchall()
        assert len(event_log_rows) == 2

    # Second poll should skip duplicates
    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox.kernel._handler_execution_exists", return_value=True):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
                result2 = await poll_inbox(limit=10, execution_id="wi_inbox_test")
    assert result2["new_count"] == 0


def test_digest_idempotent(inbox_db, monkeypatch):
    db, k = inbox_db

    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.product.notifications.default_kernel", k)

    with db.get_db() as conn:
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

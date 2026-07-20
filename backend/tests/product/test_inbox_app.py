"""Tests for proactive inbox app.

inbox_emails is a governed projection. Tests emit InboxEmail* events to set
up fixtures (mirroring the production write path).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.runtime.kernel import constants
from app.product.inbox import apply_inbox_poll_payload, generate_inbox_digest, poll_inbox


def _seed_inbox_email(
    kernel,
    *,
    email_id,
    sender="x@y.z",
    subject="t",
    preview="",
    received_at="",
    category="actionable",
    importance=0.5,
    reason="",
    status="pending",
):
    """Helper: emit an InboxEmailRecorded (+ optional status change) event."""
    kernel.emit_event(
        constants.EVENT_INBOX_EMAIL_RECORDED,
        constants.AGGREGATE_INBOX_EMAIL,
        email_id,
        payload={
            "sender": sender,
            "subject": subject,
            "preview": preview,
            "received_at": received_at,
            "category": category,
            "importance": importance,
            "reason": reason,
        },
        actor="test",
    )
    if status != "pending":
        kernel.emit_event(
            constants.EVENT_INBOX_EMAIL_STATUS_CHANGED,
            constants.AGGREGATE_INBOX_EMAIL,
            email_id,
            payload={"status": status},
            actor="test",
        )


@pytest.mark.asyncio
async def test_poll_inbox_syncs_read_status(product_kernel):
    k = product_kernel
    _seed_inbox_email(k, email_id="msg-read", subject="Read mail",
                      received_at="2026-06-10T00:00:00Z")
    _seed_inbox_email(k, email_id="msg-unread", sender="a@b.com",
                      subject="Unread", received_at="2026-06-10T00:00:00Z")

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

    async def fake_invoke(name, args=None, actor="system", **kwargs):
        return {"status": "success", "result": json.dumps(sample_unread)}

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox.kernel._handler_execution_exists", return_value=True):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
                result = await poll_inbox(limit=10, execution_id="wi_inbox_test")

    assert result["synced_read"] == 1
    rows = {r["id"]: r["status"] for r in k.query_state("inbox_emails", limit=100)}
    assert rows["msg-read"] == "read"
    assert rows["msg-unread"] == "pending"


@pytest.mark.asyncio
async def test_poll_does_not_mark_read_when_unread_beyond_email_limit(product_kernel):
    """Pending mail still UNSEEN on IMAP must not be marked read when absent from truncated emails list."""
    k = product_kernel
    _seed_inbox_email(k, email_id="msg-old-unread", sender="old@b.com",
                      subject="Older unread", received_at="2026-06-18T00:00:00Z")

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
    rows = k.query_state("inbox_emails", id="msg-old-unread")
    assert rows[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_marks_read_when_absent_from_full_unread_set(product_kernel):
    k = product_kernel
    _seed_inbox_email(k, email_id="msg-read-elsewhere", subject="Read mail",
                      received_at="2026-06-18T00:00:00Z")

    payload = {
        "count": 0,
        "unread_only": True,
        "all_unread_message_ids": [],
        "emails": [],
    }

    with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=[])):
        result = await apply_inbox_poll_payload(payload, execution_id="wi_inbox_test")

    assert result["synced_read"] == 1
    rows = k.query_state("inbox_emails", id="msg-read-elsewhere")
    assert rows[0]["status"] == "read"


@pytest.mark.asyncio
async def test_poll_inbox_dedupes_and_notifies_important(product_kernel):
    k = product_kernel
    sample = {
        "count": 2,
        "emails": [
            {"message_id": "msg-1", "from": "boss@corp.com", "subject": "Urgent",
             "preview": "Please review", "date": "2026-06-10"},
            {"message_id": "msg-2", "from": "news@shop.com", "subject": "Sale",
             "preview": "50% off", "date": "2026-06-10"},
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

    rows = k.query_state("inbox_emails", limit=10)
    assert len(rows) == 2
    assert len(k.read_events(type="InboxEmailRecorded")) == 2

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke):
        with patch("app.product.inbox.kernel._handler_execution_exists", return_value=True):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
                result2 = await poll_inbox(limit=10, execution_id="wi_inbox_test")
    assert result2["new_count"] == 0


@pytest.mark.asyncio
async def test_mark_inbox_email_status_syncs_unread_to_imap(product_kernel):
    k = product_kernel
    _seed_inbox_email(k, email_id="msg-sync-unread", status="read")

    async def fake_invoke(name, args=None, actor="user", **kwargs):
        assert name == "mark_inbox_email_unread"
        assert args["message_id"] == "msg-sync-unread"
        return {"status": "success"}

    with patch("app.product.inbox.kernel.invoke_capability", side_effect=fake_invoke) as mock_invoke:
        from app.product.inbox import mark_inbox_email_status
        await mark_inbox_email_status("msg-sync-unread", "pending")
        mock_invoke.assert_called_once()

    rows = k.query_state("inbox_emails", id="msg-sync-unread")
    assert rows[0]["status"] == "pending"


def test_digest_idempotent(product_kernel):
    k = product_kernel

    _seed_inbox_email(
        k,
        email_id="m1",
        sender="a@b.com",
        subject="Test",
        preview="preview",
        received_at="2026-07-05T00:00:00Z",
        category="actionable",
        importance=0.5,
        reason="test",
    )

    from app.product.notifications import create_notification

    with patch(
        "app.core.runtime.notification_bridge.push_notification",
        side_effect=lambda t, title, content: create_notification(t, title, content, kernel=k),
    ) as push:
        first = generate_inbox_digest()
        second = generate_inbox_digest()

    assert first is not None
    assert second is not None
    assert first["id"] == second["id"]
    push.assert_called_once()

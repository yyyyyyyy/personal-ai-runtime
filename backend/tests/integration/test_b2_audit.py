"""Integration tests for B2: Inbox / Knowledge audit events in event_log."""

import json
from unittest.mock import AsyncMock, patch

import pytest

# ── Inbox Audit Tests ──────────────────────────────────────────────────────


class TestInboxAudit:
    """Verify InboxEmailRecorded events appear in event_log after poll."""

    @pytest.mark.asyncio
    async def test_poll_inbox_emits_audit_events(self, isolated_kernel, monkeypatch):
        kernel, db = isolated_kernel

        sample = {
            "count": 1,
            "emails": [
                {
                    "message_id": "msg-audit-1",
                    "from": "boss@corp.com",
                    "subject": "Quarterly Review",
                    "preview": "Please prepare",
                    "date": "2026-06-10",
                },
            ],
        }

        async def fake_invoke(name, args=None, actor="system", **kwargs):
            return {"status": "success", "result": json.dumps(sample)}

        classified = [
            {"message_id": "msg-audit-1", "category": "important", "importance": 0.9, "reason": "Boss"},
        ]

        monkeypatch.setattr("app.product.inbox.kernel", kernel)
        # db singleton is not imported by inbox.py after inbox_emails
        # promotion to governed projection (commit 035b2f2).

        with patch.object(kernel, "invoke_capability", side_effect=fake_invoke):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
                with patch("app.core.runtime.notification_bridge.push_notification"):
                    from app.product.inbox import poll_inbox

                    result = await poll_inbox(limit=10, execution_id="wi_b2_inbox_test")

        assert result["status"] == "ok"
        assert result["new_count"] == 1

        events = kernel.read_events(aggregate_type="inbox_email")
        inbox_events = [e for e in events if e.type == "InboxEmailRecorded"]
        assert len(inbox_events) == 1
        evt = inbox_events[0]
        assert evt.payload["sender"] == "boss@corp.com"
        assert evt.payload["category"] == "important"
        assert evt.actor == "inbox"
        assert evt.caused_by == "wi_b2_inbox_test", "InboxEmailRecorded must carry execution_id via caused_by"

    @pytest.mark.asyncio
    async def test_poll_inbox_multiple_emails_audited(self, isolated_kernel, monkeypatch):
        kernel, db = isolated_kernel

        sample = {
            "count": 2,
            "emails": [
                {"message_id": "msg-a-1", "from": "a@x.com", "subject": "A", "preview": "x", "date": "2026-06-10"},
                {"message_id": "msg-a-2", "from": "b@x.com", "subject": "B", "preview": "y", "date": "2026-06-10"},
            ],
        }

        async def fake_invoke(name, args=None, actor="system", **kwargs):
            return {"status": "success", "result": json.dumps(sample)}

        classified = [
            {"message_id": "msg-a-1", "category": "important", "importance": 0.8, "reason": "Urgent"},
            {"message_id": "msg-a-2", "category": "actionable", "importance": 0.5, "reason": "Todo"},
        ]

        monkeypatch.setattr("app.product.inbox.kernel", kernel)
        # db singleton is not imported by inbox.py (see above).

        with patch.object(kernel, "invoke_capability", side_effect=fake_invoke):
            with patch("app.product.inbox._classify_emails", new=AsyncMock(return_value=classified)):
                with patch("app.core.runtime.notification_bridge.push_notification"):
                    from app.product.inbox import poll_inbox

                    result = await poll_inbox(limit=10, execution_id="wi_b2_inbox_multi")

        assert result["new_count"] == 2

        events = kernel.read_events(aggregate_type="inbox_email")
        inbox_events = [e for e in events if e.type == "InboxEmailRecorded"]
        assert len(inbox_events) == 2
        message_ids = {e.aggregate_id for e in inbox_events}
        assert "msg-a-1" in message_ids
        assert "msg-a-2" in message_ids
        for e in inbox_events:
            assert e.caused_by == "wi_b2_inbox_multi", f"InboxEmailRecorded {e.aggregate_id} must carry execution_id"

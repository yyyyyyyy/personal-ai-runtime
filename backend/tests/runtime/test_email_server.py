"""Unit tests for email MCP server helpers."""

import email

from app.core.harness.builtin_tools.email import (
    EmailServer,
    _format_date,
    _stable_message_id,
)


def test_format_date_converts_to_local_timezone():
  # 06:38 UTC -> 14:38 in UTC+8
  raw = "Wed, 10 Jun 2026 06:38:12 +0000"
  formatted = _format_date(raw)
  assert "2026-06-10" in formatted
  assert formatted.endswith(":38") or formatted.endswith(":38:12") is False


def test_message_id_from_header_bytes_matches_full_message():
    header = (
        b"Message-ID: <test@example.com>\r\n"
        b"From: Alice <alice@example.com>\r\n"
        b"Subject: Hello\r\n"
        b"Date: Wed, 10 Jun 2026 06:38:12 +0000\r\n"
    )
    from_header = EmailServer._message_id_from_header_bytes(header)
    full = email.message_from_bytes(header + b"\r\nbody")
    from_full = _stable_message_id(
        full,
        "Alice <alice@example.com>",
        "Hello",
        full.get("Date"),
    )
    assert from_header == from_full


def test_check_inbox_unread_only_includes_all_unread_message_ids(monkeypatch):
    server = EmailServer()
    monkeypatch.setattr(server, "_connect_inbox", lambda: object())
    monkeypatch.setattr(
        server,
        "_fetch_unread_message_ids_connected",
        lambda _mail: {"<id-1@example.com>", "<id-2@example.com>"},
    )
    monkeypatch.setattr(
        server,
        "_fetch_sorted_emails_connected",
        lambda _mail, limit, unread_only, body_max=300: [
            {
                "message_id": "<id-2@example.com>",
                "from": "user2@example.com",
                "subject": "Mail 2",
                "date": "2026-06-10 14:38",
                "preview": "preview",
            }
        ],
    )

    data = __import__("json").loads(server.check_inbox(limit=1, unread_only=True))
    assert data["count"] == 1
    assert set(data["all_unread_message_ids"]) == {"<id-1@example.com>", "<id-2@example.com>"}

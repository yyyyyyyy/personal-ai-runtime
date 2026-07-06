"""Tests for inbox_emails ↔ InboxEmailRecorded event consistency checks.

v0.3.0: inbox_emails is now a governed projection derived solely from events
via projectors_inbox.py. The "emit without row" drift scenario can no longer
happen in normal operation — the projector runs in the same transaction as
the event INSERT. These tests therefore focus on:
  1. Happy-path: emit produces a matching projection row.
  2. Drift detection still works when rows are inserted out-of-band (this
     can happen during manual import, raw SQL recovery, etc.).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_API_KEY", "test-key")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest

from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "inbox_consistency.db"
    db = Database(db_path=str(db_path))
    yield db, str(db_path)
    db.close()


def test_consistent_state_passes(fresh_db):
    """When inbox_emails and events are 1:1, no violations."""
    from scripts.verify_inbox_audit import (
        verify_inbox_emails_event_consistency,
    )

    db, db_path = fresh_db
    kernel = Kernel(db=db)

    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_consistent",
        payload={"sender": "x@y.z", "subject": "ok"},
        actor="inbox",
    )

    violations = verify_inbox_emails_event_consistency(db_path)
    assert violations == [], f"expected no violations, got: {violations}"


def test_inbox_row_without_event_detected(fresh_db):
    """Row in inbox_emails with no matching event → violation.

    Covers the import / raw-SQL recovery path: even though the production
    write path is now event-sourced, an out-of-band INSERT still has to be
    caught by the audit.
    """
    from scripts.verify_inbox_audit import (
        verify_inbox_emails_event_consistency,
    )

    db, db_path = fresh_db
    now = "2026-07-05T00:00:00Z"
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance,
                reason, notified, digested, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
            ("m_drift", "x@y.z", "missing event", "preview",
             now, "actionable", 0.5, "", now),
        )

    violations = verify_inbox_emails_event_consistency(db_path)
    assert any("m_drift" in v for v in violations), \
        f"expected drift detection, got: {violations}"


def test_emit_creates_projection_row(fresh_db):
    """v0.3.0: emitting InboxEmailRecorded must materialize the projection."""
    db, _ = fresh_db
    kernel = Kernel(db=db)

    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_projected",
        payload={
            "sender": "x@y.z",
            "subject": "projection test",
            "preview": "preview text",
            "received_at": "2026-07-05T00:00:00Z",
            "category": "important",
            "importance": 0.9,
            "reason": "test reason",
        },
        actor="inbox",
    )

    rows = kernel.query_state("inbox_emails", id="m_projected")
    assert len(rows) == 1
    row = rows[0]
    assert row["sender"] == "x@y.z"
    assert row["subject"] == "projection test"
    assert row["category"] == "important"
    assert row["importance"] == 0.9
    assert row["status"] == "pending"
    assert row["notified"] == 0
    assert row["digested"] == 0


def test_status_changed_event_updates_projection(fresh_db):
    """v0.3.0: InboxEmailStatusChanged transitions the projection."""
    db, _ = fresh_db
    kernel = Kernel(db=db)

    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_status",
        payload={"sender": "x@y.z", "subject": "s"},
        actor="inbox",
    )
    kernel.emit_event(
        "InboxEmailStatusChanged", "inbox_email", "m_status",
        payload={"status": "read"},
        actor="user",
    )

    rows = kernel.query_state("inbox_emails", id="m_status")
    assert rows[0]["status"] == "read"


def test_notified_and_digested_events_update_projection(fresh_db):
    """v0.3.0: InboxEmailNotified / InboxEmailDigested flip the flags."""
    db, _ = fresh_db
    kernel = Kernel(db=db)

    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_notify",
        payload={"sender": "x@y.z", "subject": "s"},
        actor="inbox",
    )
    kernel.emit_event(
        "InboxEmailNotified", "inbox_email", "m_notify",
        actor="inbox",
    )
    kernel.emit_event(
        "InboxEmailDigested", "inbox_email", "digest_1",
        actor="inbox",
    )

    rows = kernel.query_state("inbox_emails", id="m_notify")
    assert rows[0]["notified"] == 1
    assert rows[0]["digested"] == 1


def test_inbox_email_rebuild_byte_identical(fresh_db):
    """v0.3.0: rebuild('inbox_email') produces a byte-identical projection."""
    db, _ = fresh_db
    kernel = Kernel(db=db)

    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_rebuild_a",
        payload={"sender": "a@x", "subject": "a", "category": "important"},
        actor="inbox",
    )
    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_rebuild_b",
        payload={"sender": "b@x", "subject": "b"},
        actor="inbox",
    )
    kernel.emit_event(
        "InboxEmailStatusChanged", "inbox_email", "m_rebuild_a",
        payload={"status": "handled"},
        actor="user",
    )

    before = kernel.query_state("inbox_emails", limit=100)
    kernel.rebuild("inbox_email")
    after = kernel.query_state("inbox_emails", limit=100)
    assert before == after

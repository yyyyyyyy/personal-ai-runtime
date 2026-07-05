"""Tests for inbox_emails ↔ InboxEmailRecorded event consistency checks."""

import os
import sqlite3
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

    # Insert matching pair
    now = "2026-07-05T00:00:00Z"
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance,
                reason, notified, digested, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
            ("m_consistent", "x@y.z", "ok", "preview",
             now, "actionable", 0.5, "", now),
        )
    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "m_consistent",
        payload={"sender": "x@y.z", "subject": "ok"},
        actor="inbox",
    )

    violations = verify_inbox_emails_event_consistency(db_path)
    assert violations == [], f"expected no violations, got: {violations}"


def test_inbox_row_without_event_detected(fresh_db):
    """Row in inbox_emails with no matching event → violation."""
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


def test_event_without_row_under_threshold_no_violation(fresh_db):
    """A few events without rows are tolerated (legacy/user-deleted emails)."""
    from scripts.verify_inbox_audit import (
        verify_inbox_emails_event_consistency,
    )

    db, db_path = fresh_db
    kernel = Kernel(db=db)

    # Emit a few InboxEmailRecorded events with no inbox_emails rows
    for i in range(5):
        kernel.emit_event(
            "InboxEmailRecorded", "inbox_email", f"m_legacy_{i}",
            payload={"sender": "x@y.z", "subject": "legacy"},
            actor="inbox",
        )

    violations = verify_inbox_emails_event_consistency(db_path)
    # 5 < threshold of 20, no violations expected
    assert violations == [], \
        f"legacy events below threshold should not flag, got: {violations}"


def test_many_events_without_row_flagged(fresh_db):
    """> 20 events without rows indicate systemic drift and are flagged."""
    from scripts.verify_inbox_audit import (
        verify_inbox_emails_event_consistency,
    )

    db, db_path = fresh_db
    kernel = Kernel(db=db)

    for i in range(25):
        kernel.emit_event(
            "InboxEmailRecorded", "inbox_email", f"m_mass_{i}",
            payload={"sender": "x@y.z", "subject": "mass"},
            actor="inbox",
        )

    violations = verify_inbox_emails_event_consistency(db_path)
    assert len(violations) >= 1, "expected systemic drift to be flagged"
    assert any("m_mass_" in v for v in violations)

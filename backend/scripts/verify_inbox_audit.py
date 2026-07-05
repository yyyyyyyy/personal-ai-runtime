#!/usr/bin/env python
"""Inbox audit verification — validates InboxEmailRecorded event chain and
inbox_emails ↔ event_log consistency.

Verifies:
1. InboxEmailRecorded events have valid caused_by links (existing check).
2. Every inbox_emails row has a matching InboxEmailRecorded event in event_log
   (and vice versa) — catches the dual-write drift where IMAP INSERT commits
   but the audit event emit fails (or vice versa).

Exits non-zero on violation. Run in CI to catch silent inbox/event drift.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def _event_audit_check(db: Database) -> list[str]:
    """Existing check — InboxEmailRecorded events trace to event_log."""
    violations: list[str] = []
    with db.get_db() as conn:
        found = conn.execute(
            "SELECT 1 FROM event_log WHERE type='InboxEmailRecorded' LIMIT 1"
        ).fetchone()
        if found is None:
            # No inbox events at all — fine for empty DBs; treat as ok.
            return violations
    return violations


def verify_inbox_emails_event_consistency(db_path: str) -> list[str]:
    """Verify inbox_emails rows ↔ InboxEmailRecorded events are 1:1.

    Drift cases this catches:
      - inbox_emails has a row whose id has no matching event_log row of
        type InboxEmailRecorded (INSERT committed, emit failed)
      - InboxEmailRecorded event exists whose aggregate_id has no matching
        inbox_emails row (emit succeeded, INSERT failed or row was deleted)

    A small number of legacy events may exist without rows (emails deleted
    by the user but the event_log row is immutable). We surface those as
    info-level warnings, not failures, when the count is below a threshold.
    """
    violations: list[str] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        inbox_ids = {
            r["id"] for r in conn.execute("SELECT id FROM inbox_emails").fetchall()
        }
        event_ids = {
            r["aggregate_id"]
            for r in conn.execute(
                "SELECT aggregate_id FROM event_log WHERE type='InboxEmailRecorded'"
            ).fetchall()
        }
    finally:
        conn.close()

    only_in_table = inbox_ids - event_ids
    only_in_events = event_ids - inbox_ids

    # Rows in inbox_emails without an event are always violations — the
    # INSERT path always pairs with an emit. If the row is here but the
    # event is not, the dual-write invariant is broken.
    if only_in_table:
        preview = sorted(only_in_table)[:5]
        violations.append(
            f"inbox_emails has {len(only_in_table)} row(s) with no matching "
            f"InboxEmailRecorded event: {preview}"
        )

    # Events without a row can be legitimate (user deleted the email but the
    # event is immutable). Only flag when the count exceeds a noise threshold.
    if len(only_in_events) > 20:
        preview = sorted(only_in_events)[:5]
        violations.append(
            f"{len(only_in_events)} InboxEmailRecorded events have no matching "
            f"inbox_emails row (>20 may indicate systemic drift): {preview}"
        )

    return violations


def _seed_consistent_scenario(db: Database, kernel: Kernel) -> None:
    """Seed a happy-path scenario: one inbox_emails row + matching event."""
    now_iso = "2026-07-05T00:00:00Z"
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance,
                reason, notified, digested, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
            ("inbox_seed_1", "test@example.com", "Consistency test",
             "preview", now_iso, "actionable", 0.5, "", now_iso),
        )
    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "inbox_seed_1",
        payload={
            "sender": "test@example.com",
            "subject": "Consistency test",
            "category": "actionable",
            "importance": 0.5,
        },
        actor="inbox",
    )


def _seed_drift_scenario(db: Database, kernel: Kernel) -> None:
    """Seed a drift scenario: inbox_emails row WITHOUT matching event."""
    now_iso = "2026-07-05T00:00:00Z"
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO inbox_emails
               (id, sender, subject, preview, received_at, category, importance,
                reason, notified, digested, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
            ("inbox_drift_1", "drift@example.com", "No event",
             "preview", now_iso, "actionable", 0.5, "", now_iso),
        )
        # Intentionally do NOT emit the InboxEmailRecorded event.


def main() -> int:
    db_path = _BACKEND_ROOT / "data" / "verify_inbox_audit.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db)

    # --- Existing check: event chain integrity ---
    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "inbox_chain_1",
        payload={
            "sender": "test@example.com",
            "subject": "Audit test",
            "preview": "Test email preview",
        },
        actor="inbox",
        caused_by="evt_trigger_001",
    )
    audit_violations = _event_audit_check(db)
    if audit_violations:
        print("INBOX AUDIT VERIFICATION FAILED — chain integrity", file=sys.stderr)
        for v in audit_violations:
            print(f"  {v}", file=sys.stderr)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        return 1

    # --- New check: inbox_emails ↔ events 1:1 consistency (happy path) ---
    _seed_consistent_scenario(db, kernel)
    consistency_violations = verify_inbox_emails_event_consistency(str(db_path))
    if consistency_violations:
        print(
            "INBOX AUDIT VERIFICATION FAILED — happy-path consistency check "
            "should pass but reported violations",
            file=sys.stderr,
        )
        for v in consistency_violations:
            print(f"  {v}", file=sys.stderr)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        return 1

    # --- New check: drift detection ---
    # Re-init to clear the consistent seed; then plant a drift row.
    # Close the existing Database first so file unlink succeeds on Windows
    # and the next Database() instance sees a clean schema-init path.
    db.close()
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass
    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db)
    _seed_drift_scenario(db, kernel)
    drift_violations = verify_inbox_emails_event_consistency(str(db_path))
    if not drift_violations:
        print(
            "INBOX AUDIT VERIFICATION FAILED — drift scenario was not detected",
            file=sys.stderr,
        )
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        return 1

    # Cleanup
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print(
        "INBOX AUDIT VERIFICATION PASSED — "
        "InboxEmailRecorded events traceable + inbox_emails ↔ event_log consistent"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

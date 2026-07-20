#!/usr/bin/env python
"""Inbox audit verification — validates InboxEmailRecorded event chain and
inbox_emails <-> event_log consistency.

Verifies:
1. InboxEmailRecorded events preserve caused_by links.
2. Every inbox_emails row has a matching InboxEmailRecorded event in event_log
   (and vice versa) — catches the dual-write drift where IMAP INSERT commits
   but the audit event emit fails (or vice versa).

Exits non-zero on violation. Run in CI to catch silent inbox/event drift.
"""

from __future__ import annotations

from pathlib import Path

import sqlite3
import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel, prepare_script_env

prepare_script_env()

from app.core.runtime.kernel import Kernel  # noqa: E402
from app.store.database import Database  # noqa: E402


def verify_caused_by_chain(
    db: Database,
    *,
    aggregate_id: str,
    expected_caused_by: str,
) -> list[str]:
    """Verify InboxEmailRecorded.caused_by is preserved on the seeded event."""
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT caused_by FROM event_log "
            "WHERE type='InboxEmailRecorded' AND aggregate_id=? LIMIT 1",
            (aggregate_id,),
        ).fetchone()
    if row is None:
        return [f"missing InboxEmailRecorded for aggregate_id={aggregate_id!r}"]
    if row["caused_by"] != expected_caused_by:
        return [
            f"caused_by mismatch for {aggregate_id!r}: "
            f"got {row['caused_by']!r}, expected {expected_caused_by!r}"
        ]
    return []


def verify_inbox_emails_event_consistency(db_path: str) -> list[str]:
    """Verify inbox_emails rows <-> InboxEmailRecorded events are 1:1."""
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

    if only_in_table:
        preview = sorted(only_in_table)[:5]
        violations.append(
            f"inbox_emails has {len(only_in_table)} row(s) with no matching "
            f"InboxEmailRecorded event: {preview}"
        )

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


def main() -> int:
    with ephemeral_kernel("verify_inbox_audit.db") as (db, kernel):
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
        audit_violations = verify_caused_by_chain(
            db,
            aggregate_id="inbox_chain_1",
            expected_caused_by="evt_trigger_001",
        )
        if audit_violations:
            print("INBOX AUDIT VERIFICATION FAILED — chain integrity", file=sys.stderr)
            for v in audit_violations:
                print(f"  {v}", file=sys.stderr)
            return 1

        _seed_consistent_scenario(db, kernel)
        consistency_violations = verify_inbox_emails_event_consistency(db.db_path)
        if consistency_violations:
            print(
                "INBOX AUDIT VERIFICATION FAILED — happy-path consistency check "
                "should pass but reported violations",
                file=sys.stderr,
            )
            for v in consistency_violations:
                print(f"  {v}", file=sys.stderr)
            return 1

    # Fresh DB for drift detection (previous ephemeral file is cleaned up).
    with ephemeral_kernel("verify_inbox_audit.db") as (db, kernel):
        _seed_drift_scenario(db, kernel)
        drift_violations = verify_inbox_emails_event_consistency(db.db_path)
        if not drift_violations:
            print(
                "INBOX AUDIT VERIFICATION FAILED — drift scenario was not detected",
                file=sys.stderr,
            )
            return 1

    print(
        "INBOX AUDIT VERIFICATION PASSED — "
        "InboxEmailRecorded events traceable + inbox_emails <-> event_log consistent"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

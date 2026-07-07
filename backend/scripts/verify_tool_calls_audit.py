#!/usr/bin/env python
"""Verify tool_calls ↔ Capability* events 1:1 consistency.

tool_calls is a governed projection derived solely from CapabilityInvoked,
CapabilityFailed, and CapabilityDenied events via projectors_telemetry.py.
This script checks that every tool_calls row has a corresponding event in
event_log and vice versa.

Usage:
    python scripts/verify_tool_calls_audit.py
    python scripts/verify_tool_calls_audit.py --db backend/data/*.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _connect(db_path: str):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def verify(db_path: str) -> int:
    conn = _connect(db_path)

    # tool_calls row count
    tc_total = conn.execute("SELECT COUNT(*) AS c FROM tool_calls").fetchone()["c"]

    # Capability* event count (Invoked, Failed, Denied)
    ce_total = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE type IN (?, ?, ?)",
        ("CapabilityInvoked", "CapabilityFailed", "CapabilityDenied"),
    ).fetchone()["c"]

    violations = 0

    if tc_total != ce_total:
        print(
            f"MISMATCH: tool_calls={tc_total} != Capability* events={ce_total}"
        )
        violations += 1

    # Check: every tool_calls row has its event_log counterpart
    orphan_rows = conn.execute(
        """SELECT tc.id, tc.tool_name FROM tool_calls tc
           WHERE NOT EXISTS (
               SELECT 1 FROM event_log el
               WHERE el.seq = CAST(SUBSTR(tc.id, 4) AS INTEGER)
                 AND el.type IN ('CapabilityInvoked','CapabilityFailed','CapabilityDenied')
           )"""
    ).fetchall()
    for row in orphan_rows:
        print(f"ORPHAN tool_calls row: {row['id']} ({row['tool_name']})")
        violations += 1

    # Check: every Capability* event has its tool_calls counterpart
    orphan_events = conn.execute(
        """SELECT el.seq, el.type, el.payload FROM event_log el
           WHERE el.type IN ('CapabilityInvoked','CapabilityFailed','CapabilityDenied')
             AND NOT EXISTS (
                 SELECT 1 FROM tool_calls tc
                 WHERE tc.id = 'tc_' || CAST(el.seq AS TEXT)
           )"""
    ).fetchall()
    for row in orphan_events:
        import json as _json
        try:
            p = _json.loads(row["payload"])
            name = p.get("name", "?")
        except Exception:
            name = "?"
        print(f"ORPHAN event: seq={row['seq']} type={row['type']} name={name}")
        violations += 1

    conn.close()

    if violations:
        print(f"\nFAIL: {violations} violation(s) found")
        return 1
    print(f"PASS: tool_calls ({tc_total}) ↔ Capability* events ({ce_total}) 1:1")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify tool_calls governed projection integrity"
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        data_dir = ROOT / "data"
        candidates = sorted(data_dir.glob("*.db"))
        if not candidates:
            print("No *.db found in data/. Use --db to specify path.")
            return 0
        db_path = str(candidates[0])

    return verify(db_path)


if __name__ == "__main__":
    sys.exit(main())

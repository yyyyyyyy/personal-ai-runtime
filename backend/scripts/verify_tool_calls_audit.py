#!/usr/bin/env python
"""Verify tool_calls ↔ Capability* events 1:1 consistency.

tool_calls is a governed projection derived solely from CapabilityInvoked,
CapabilityFailed, and CapabilityDenied events via projectors_governance.py.
This script checks that every tool_calls row has a corresponding event in
event_log and vice versa.

Usage:
    python -m scripts.verify_tool_calls_audit              # self-test (CI)
    python -m scripts.verify_tool_calls_audit --db path.db # audit an existing DB
"""
from __future__ import annotations

from pathlib import Path

import argparse
import json
import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel

CAPABILITY_EVENT_TYPES = (
    "CapabilityInvoked",
    "CapabilityFailed",
    "CapabilityDenied",
)


def _connect(db_path: str):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def verify(db_path: str) -> int:
    conn = _connect(db_path)

    tc_total = conn.execute("SELECT COUNT(*) AS c FROM tool_calls").fetchone()["c"]
    ce_total = conn.execute(
        "SELECT COUNT(*) AS c FROM event_log WHERE type IN (?, ?, ?)",
        CAPABILITY_EVENT_TYPES,
    ).fetchone()["c"]

    violations = 0

    if tc_total != ce_total:
        print(f"MISMATCH: tool_calls={tc_total} != Capability* events={ce_total}")
        violations += 1

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

    orphan_events = conn.execute(
        """SELECT el.seq, el.type, el.payload FROM event_log el
           WHERE el.type IN ('CapabilityInvoked','CapabilityFailed','CapabilityDenied')
             AND NOT EXISTS (
                 SELECT 1 FROM tool_calls tc
                 WHERE tc.id = 'tc_' || CAST(el.seq AS TEXT)
           )"""
    ).fetchall()
    for row in orphan_events:
        try:
            name = json.loads(row["payload"]).get("name", "?")
        except Exception:
            name = "?"
        print(f"ORPHAN event: seq={row['seq']} type={row['type']} name={name}")
        violations += 1

    conn.close()

    if violations:
        print(f"\nFAIL: {violations} violation(s) found")
        return 1
    print(f"PASS: tool_calls ({tc_total}) <-> Capability* events ({ce_total}) 1:1")
    return 0


def run_self_test() -> int:
    """Emit Capability* events into an isolated DB and assert 1:1 projection."""
    with ephemeral_kernel("verify_tool_calls_audit.db") as (db, kernel):
        kernel.emit_event(
            "CapabilityInvoked",
            "capability",
            "cap_read_file",
            payload={"name": "read_file", "latency_ms": 1.5},
            actor="verify",
        )
        kernel.emit_event(
            "CapabilityFailed",
            "capability",
            "cap_shell_exec",
            payload={"name": "shell_exec", "error": "boom", "latency_ms": 2.0},
            actor="verify",
        )
        kernel.emit_event(
            "CapabilityDenied",
            "capability",
            "cap_forbidden",
            payload={"name": "forbidden_tool", "reason": "policy"},
            actor="verify",
        )
        return verify(db.db_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify tool_calls governed projection integrity"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (default: isolated self-test)",
    )
    args = parser.parse_args()

    if args.db:
        return verify(args.db)
    return run_self_test()


if __name__ == "__main__":
    sys.exit(main())

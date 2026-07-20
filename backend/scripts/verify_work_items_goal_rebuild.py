#!/usr/bin/env python
"""Verify work_items goal rebuild.

Tests that the WorkItemCreated/Updated/StatusChanged projectors produce
byte-identical state for work_type='goal' rows when the work_item aggregate
is rebuilt from event_log.

Exit codes:
  0 — rebuild byte-identical
  1 — drift detected
"""
from __future__ import annotations

from pathlib import Path

import sys
from typing import Any

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel

SCENARIO: list[tuple] = [
    ("WorkItemCreated", "work_item", "wg_1", {
        "title": "Run a marathon",
        "work_type": "goal",
        "status": "active",
        "progress": 0.0,
        "importance": 0.9,
        "urgency": 0.4,
        "deadline": "2026-12-01T00:00:00Z",
    }),
    ("WorkItemUpdated", "work_item", "wg_1", {
        "progress": 0.1,
        "urgency": 0.6,
    }),
    ("WorkItemCreated", "work_item", "wc_1", {
        "title": "Buy running shoes",
        "work_type": "task",
        "parent_work_id": "wg_1",
    }),
    ("WorkItemCreated", "work_item", "wc_2", {
        "title": "Train 3x per week",
        "work_type": "task",
        "parent_work_id": "wg_1",
    }),
    ("WorkItemStatusChanged", "work_item", "wc_1", {"status": "completed"}),
    ("WorkItemCreated", "work_item", "wc_3", {
        "title": "Legacy action",
        "work_type": "task",
        "parent_goal_id": "wg_1",
    }),
]


def snapshot(db: Any, table: str) -> list[dict]:
    with db.get_db() as conn:
        return [
            dict(r) for r in conn.execute(
                f"SELECT * FROM {table} WHERE id IN ('wg_1','wc_1','wc_2','wc_3') "
                f"ORDER BY id"
            ).fetchall()
        ]


def main() -> int:
    with ephemeral_kernel("verify_work_items_goal_rebuild.db") as (db, kernel):
        for evt in SCENARIO:
            evt_type, agg_type, agg_id, payload = evt
            kernel.emit_event(evt_type, agg_type, agg_id, payload=payload, actor="verify")

        before = snapshot(db, "work_items")

        parent_before = next((r for r in before if r["id"] == "wg_1"), None)
        if parent_before is None:
            print("FAIL: parent goal missing", file=sys.stderr)
            return 1
        if parent_before["work_type"] != "goal":
            print(f"FAIL: expected work_type=goal, got {parent_before['work_type']!r}",
                  file=sys.stderr)
            return 1
        if parent_before["importance"] != 0.9:
            print(f"FAIL: expected importance=0.9, got {parent_before['importance']!r}",
                  file=sys.stderr)
            return 1
        if parent_before["deadline"] != "2026-12-01T00:00:00Z":
            print(f"FAIL: unexpected deadline {parent_before['deadline']!r}",
                  file=sys.stderr)
            return 1
        if abs(parent_before["progress"] - 1 / 3) >= 1e-6:
            print(
                f"FAIL: expected progress 1/3, got {parent_before['progress']}",
                file=sys.stderr,
            )
            return 1

        result = kernel.rebuild("work_item")
        print(f"  rebuild('work_item'): {result} events")

        after = snapshot(db, "work_items")

        if before != after:
            print("WORK_ITEMS GOAL REBUILD FAILED — drift detected", file=sys.stderr)
            for b, a in zip(before, after):
                if b != a:
                    print(f"  row {b['id']}:", file=sys.stderr)
                    for key in set(b) | set(a):
                        if b.get(key) != a.get(key):
                            print(
                                f"    {key}: before={b.get(key)!r} after={a.get(key)!r}",
                                file=sys.stderr,
                            )
            return 1

    print("WORK_ITEMS GOAL REBUILD PASSED — goal fields + derived progress byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())

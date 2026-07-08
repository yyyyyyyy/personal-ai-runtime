#!/usr/bin/env python
"""Verify work_items goal rebuild (v1.0 Phase 3d).

Tests that the WorkItemCreated/Updated/StatusChanged projectors produce
byte-identical state for work_type='goal' rows when the work_item aggregate
is rebuilt from event_log. This complements verify_goal_rebuild.py (which
validates the legacy goals projection) and will supersede it in Phase 4
when the goals table is dropped.

Exit codes:
  0 — rebuild byte-identical
  1 — drift detected
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database

SCENARIO: list[tuple] = [
    # Create a parent goal
    ("WorkItemCreated", "work_item", "wg_1", {
        "title": "Run a marathon",
        "work_type": "goal",
        "status": "active",
        "progress": 0.0,
        "importance": 0.9,
        "urgency": 0.4,
        "deadline": "2026-12-01T00:00:00Z",
    }),
    # Update goal fields
    ("WorkItemUpdated", "work_item", "wg_1", {
        "progress": 0.1,
        "urgency": 0.6,
    }),
    # Children linked via parent_work_id (v1.0 unified)
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
    # Complete one child — projector should recompute parent progress to 0.5
    ("WorkItemStatusChanged", "work_item", "wc_1", {"status": "completed"}),
    # Children linked via parent_goal_id (legacy pattern from /api/goals/{id}/actions)
    ("WorkItemCreated", "work_item", "wc_3", {
        "title": "Legacy action",
        "work_type": "task",
        "parent_goal_id": "wg_1",
    }),
]


def snapshot(db: Database, table: str) -> list[dict]:
    with db.get_db() as conn:
        return [
            dict(r) for r in conn.execute(
                f"SELECT * FROM {table} WHERE id IN ('wg_1','wc_1','wc_2','wc_3') "
                f"ORDER BY id"
            ).fetchall()
        ]


def main() -> int:
    db_path = _BACKEND_ROOT / "data" / "verify_work_items_goal_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db)

    for evt in SCENARIO:
        evt_type, agg_type, agg_id, payload = evt
        kernel.emit_event(evt_type, agg_type, agg_id, payload=payload, actor="verify")

    before = snapshot(db, "work_items")

    # Sanity assertions before rebuild
    parent_before = next((r for r in before if r["id"] == "wg_1"), None)
    assert parent_before is not None, "parent goal missing"
    assert parent_before["work_type"] == "goal"
    assert parent_before["importance"] == 0.9
    assert parent_before["deadline"] == "2026-12-01T00:00:00Z"
    # 1 of 3 children completed → progress = 1/3
    assert abs(parent_before["progress"] - 1/3) < 1e-6, (
        f"expected progress 1/3, got {parent_before['progress']}"
    )

    # Rebuild
    result = kernel.rebuild("work_item")
    print(f"  rebuild('work_item'): {result} events")

    after = snapshot(db, "work_items")

    # Byte-identical assertion
    if before != after:
        print("WORK_ITEMS GOAL REBUILD FAILED — drift detected", file=sys.stderr)
        for b, a in zip(before, after):
            if b != a:
                print(f"  row {b['id']}:", file=sys.stderr)
                for k in set(b) | set(a):
                    if b.get(k) != a.get(k):
                        print(f"    {k}: before={b.get(k)!r} after={a.get(k)!r}", file=sys.stderr)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        return 1

    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print("WORK_ITEMS GOAL REBUILD PASSED — goal fields + derived progress byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())

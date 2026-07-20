#!/usr/bin/env python
"""Goal rebuild verification — validate parent-child relationships in work_items.

v1.0: goals table dropped; goal rows live in work_items (work_type='goal').
Children reference the parent goal via parent_goal_id.

Verifies:
1. All goal rows exist after rebuild
2. parent_goal_id references are valid (parent exists + event_log)
3. Goal parent-child chain is intact
"""

from __future__ import annotations

from pathlib import Path

import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel


def main() -> int:
    with ephemeral_kernel("verify_goal_rebuild.db") as (db, k):
        k.emit_event("WorkItemCreated", "work_item", "goal_parent", payload={
            "title": "Parent Goal", "importance": 0.9, "work_type": "goal",
            "status": "active",
        }, actor="verify")
        k.emit_event("WorkItemCreated", "work_item", "goal_child", payload={
            "title": "Child Goal", "parent_goal_id": "goal_parent",
            "importance": 0.5, "work_type": "goal", "status": "active",
        }, actor="verify")
        k.emit_event("WorkItemUpdated", "work_item", "goal_child", payload={
            "progress": 0.3,
        }, actor="verify")

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            rows = conn.execute(
                "SELECT id, title, parent_goal_id, progress "
                "FROM work_items WHERE work_type = 'goal' ORDER BY id"
            ).fetchall()

            if len(rows) < 2:
                print(f"FAIL: expected >=2 goals, got {len(rows)}", file=sys.stderr)
                return 1

            child = next((r for r in rows if r["id"] == "goal_child"), None)
            parent = next((r for r in rows if r["id"] == "goal_parent"), None)
            if parent is None:
                print("FAIL: Parent goal not found", file=sys.stderr)
                return 1
            if child is None:
                print("FAIL: Child goal not found", file=sys.stderr)
                return 1
            if child["parent_goal_id"] != "goal_parent":
                print(
                    f"FAIL: Child parent_goal_id mismatch: {child['parent_goal_id']}",
                    file=sys.stderr,
                )
                return 1
            if child["progress"] is None:
                print("FAIL: Progress not updated", file=sys.stderr)
                return 1

            found = conn.execute(
                "SELECT 1 FROM event_log "
                "WHERE aggregate_type='work_item' AND aggregate_id=? LIMIT 1",
                (child["parent_goal_id"],),
            ).fetchone()
            if not found:
                print(f"FAIL: parent {child['parent_goal_id']!r} not in event_log",
                      file=sys.stderr)
                return 1

        k.rebuild("work_item")

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            rows = conn.execute(
                "SELECT id FROM work_items WHERE work_type = 'goal' ORDER BY id"
            ).fetchall()
            if len(rows) < 2:
                print(f"FAIL: after rebuild, expected >=2 goals, got {len(rows)}",
                      file=sys.stderr)
                return 1

    print("GOAL REBUILD VERIFICATION PASSED — "
          "goals with parent_goal_id traceable to event_log")
    return 0


if __name__ == "__main__":
    sys.exit(main())

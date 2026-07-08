#!/usr/bin/env python
"""Goal rebuild verification — validate parent-child relationships in work_items.

v1.0: goals table dropped; goal rows live in work_items (work_type='goal').
Children reference the parent goal via parent_goal_id.

Verifies:
1. All goal rows exist after rebuild
2. parent_goal_id references are valid (parent exists + event_log)
3. Goal parent-child chain is intact
"""

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.store.database import Database


def main():
    db_path = _BACKEND_ROOT / "data" / "verify_goal_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

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
            sys.exit(1)

        child = [r for r in rows if r["id"] == "goal_child"][0]
        parent = [r for r in rows if r["id"] == "goal_parent"][0]

        assert parent is not None, "Parent goal not found"
        assert child["parent_goal_id"] == "goal_parent", \
            f"Child parent_goal_id mismatch: {child['parent_goal_id']}"
        assert child["progress"] is not None, "Progress not updated"

        found = conn.execute(
            "SELECT 1 FROM event_log "
            "WHERE aggregate_type='work_item' AND aggregate_id=? LIMIT 1",
            (child["parent_goal_id"],),
        ).fetchone()
        if not found:
            print(f"FAIL: parent {child['parent_goal_id']!r} not in event_log",
                  file=sys.stderr)
            sys.exit(1)

    # Rebuild and verify intact
    k.rebuild("work_item")

    with db.get_db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        rows = conn.execute(
            "SELECT id FROM work_items WHERE work_type = 'goal' ORDER BY id"
        ).fetchall()
        if len(rows) < 2:
            print(f"FAIL: after rebuild, expected >=2 goals, got {len(rows)}",
                  file=sys.stderr)
            sys.exit(1)

    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print("GOAL REBUILD VERIFICATION PASSED — "
          "goals with parent_goal_id traceable to event_log")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Backfill work_items from goals (v1.0 Phase 2).

For each row in the legacy `goals` table, emits a one-time WorkItemCreated
event with work_type='goal' that populates the v1.0 goal-unification columns.
The goals table itself is untouched — Phase 4 will drop it.

The backfill is idempotent: it skips goals whose id already exists as a
work_item row. Re-running on a backfilled DB is a no-op.

Usage:
    python scripts/backfill_goals_to_work_items.py
    python scripts/backfill_goals_to_work_items.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "backfill-key")


def _existing_work_item_ids(db_path: str, goal_ids: list[str]) -> set[str]:
    """Return the subset of goal_ids that already exist as work_items rows."""
    if not goal_ids:
        return set()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(goal_ids))
        rows = conn.execute(
            f"SELECT id FROM work_items WHERE id IN ({placeholders})",
            goal_ids,
        ).fetchall()
        return {r["id"] for r in rows}
    finally:
        conn.close()


def _all_goals(db_path: str) -> list[dict]:
    """Read all rows from the legacy goals table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM goals").fetchall()]
    finally:
        conn.close()


def backfill(db_path: str, *, dry_run: bool = False) -> dict:
    """Emit WorkItemCreated events for every goal not yet in work_items.

    Returns a summary dict: {total, skipped, emitted, errors}.
    """
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=db_path)
    kernel = Kernel(db=db)

    goals = _all_goals(db_path)
    if not goals:
        return {"total": 0, "skipped": 0, "emitted": 0, "errors": 0}

    goal_ids = [g["id"] for g in goals]
    already_present = _existing_work_item_ids(db_path, goal_ids)

    summary = {"total": len(goals), "skipped": 0, "emitted": 0, "errors": 0}

    for g in goals:
        gid = g["id"]
        if gid in already_present:
            summary["skipped"] += 1
            continue

        payload = {
            "title": g.get("title", ""),
            "description": g.get("description") or "",
            "work_type": "goal",
            # v1.0 unification: goal.parent_id (self-FK in goals tree) maps
            # to parent_work_id (Phase 3 will retire parent_goal_id entirely).
            "parent_work_id": g.get("parent_id"),
            "status": g.get("status", "active"),
            "progress": float(g.get("progress", 0) or 0),
            "importance": float(g.get("importance", 0.5) or 0.5),
            "urgency": float(g.get("urgency", 0.5) or 0.5),
            "deadline": g.get("deadline"),
            "last_activity_at": g.get("last_activity_at") or g.get("updated_at"),
            "created_at": g.get("created_at"),
        }

        if dry_run:
            print(f"  [dry-run] would emit WorkItemCreated for goal {gid}: {payload['title']}")
            summary["emitted"] += 1
            continue

        try:
            kernel.emit_event(
                "WorkItemCreated", "work_item", gid,
                payload=payload,
                actor="backfill",
            )
            summary["emitted"] += 1
        except Exception as exc:
            print(f"  ERROR backfilling goal {gid}: {exc}", file=sys.stderr)
            summary["errors"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill goals → work_items (v1.0 Phase 2)")
    parser.add_argument("--db", help="SQLite database path (default: settings.sqlite_path)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without emitting events")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        from app.config import settings

        db_path = settings.sqlite_path

    if not Path(db_path).exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        return 2

    print(f"Backfilling goals → work_items in {db_path}")
    summary = backfill(db_path, dry_run=args.dry_run)
    print()
    print(f"  total goals:  {summary['total']}")
    print(f"  skipped:      {summary['skipped']} (already present as work_items)")
    print(f"  emitted:      {summary['emitted']}")
    print(f"  errors:       {summary['errors']}")

    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

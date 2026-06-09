#!/usr/bin/env python
"""Rebuild verification guard: replay the Event Log and verify projections.

This script emits a set of sample events, snapshots the projection tables,
performs a full rebuild, then asserts the post-rebuild state is identical.
Non-zero exit means the Event Log cannot reconstruct State — a Runtime invariant
violation that must block CI.
"""

import os
import sys

os.environ.setdefault("LLM_API_KEY", "test-key")

from pathlib import Path
from typing import Any

from app.core.runtime.kernel import Kernel
from app.store.database import Database

SAMPLE_SCENARIO: list[tuple[str, str, str, dict[str, Any]]] = [
    # Goals
    ("GoalCreated", "goal", "g1", {"title": "Project Alpha", "importance": 0.9}),
    ("GoalCreated", "goal", "g2", {"title": "Learn Zig", "urgency": 0.7}),
    ("GoalUpdated", "goal", "g1", {"progress": 0.5}),
    ("GoalCompleted", "goal", "g2", {}),
    ("GoalDeleted", "goal", "g1", {}),
    # Approvals
    ("ApprovalRequested", "approval", "apr1", {"action": "write_file", "risk": "high", "ctx": {}}),
    ("ApprovalGranted", "approval", "apr1", {}),
    # Memories
    ("MemoryDerived", "memory", "m1", {"category": "fact", "content": "Likes Rust", "confidence": 0.8}),
    ("MemoryUpdated", "memory", "m1", {"content": "Prefers Rust", "confidence": 0.9}),
    ("MemoryDeleted", "memory", "m1", {}),
    # Tasks
    ("TaskCreated", "task", "t1", {
        "name": "Ship feature",
        "description": "Build runtime",
        "parent_task_id": None,
        "dependencies_json": None,
        "priority": 1,
    }),
    ("TaskStatusChanged", "task", "t1", {"status": "running"}),
    ("TaskCompleted", "task", "t1", {}),
]


def snapshot(db: Database, tables: list[str]) -> dict:
    with db.get_db() as conn:
        return {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()]
            for t in tables
        }


def main():
    db_path = Path(__file__).resolve().parent.parent / "data" / "verify_rebuild.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    tables = ["goals", "approvals", "memories", "tasks"]

    # 1. Emit sample scenario
    for evt in SAMPLE_SCENARIO:
        k.emit_event(*evt[:3], payload=evt[3] if len(evt) > 3 else {}, actor="verify")

    before = snapshot(db, tables)

    # 2. Rebuild all registered aggregate types
    result = k.rebuild_all()
    for at in sorted(result):
        print(f"  rebuild({at!r}): {result[at]} events")

    after = snapshot(db, tables)

    # 3. Assert identity
    failed = False
    for t in tables:
        if before.get(t) != after.get(t):
            print(f"FAIL: {t!r} projection differs after rebuild", file=sys.stderr)
            print(f"  before: {len(before.get(t, []))} rows", file=sys.stderr)
            print(f"  after:  {len(after.get(t, []))} rows", file=sys.stderr)
            failed = True

    # Cleanup (best-effort; may fail on Windows due to WAL locks)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    if failed:
        print("REBUILD VERIFICATION FAILED — Event Log cannot reconstruct State", file=sys.stderr)
        sys.exit(1)

    print("REBUILD VERIFICATION PASSED — all projections byte-identical after rebuild")


if __name__ == "__main__":
    main()

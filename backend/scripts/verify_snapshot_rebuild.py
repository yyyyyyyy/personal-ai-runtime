#!/usr/bin/env python
"""Verify incremental rebuild from projection checkpoint."""

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


def snapshot_work_items(db: Database) -> list[dict]:
    with db.get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM goals ORDER BY id").fetchall()]


def read_checkpoint_seq(db: Database, aggregate_type: str) -> int | None:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT last_applied_seq FROM projection_checkpoints WHERE aggregate_type = ?",
            (aggregate_type,),
        ).fetchone()
    return int(row["last_applied_seq"]) if row else None


def main() -> int:
    db_path = _BACKEND_ROOT / "data" / "verify_snapshot.db"
    if db_path.exists():
        db_path.unlink()

    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    k.emit_event("WorkItemCreated", "work_item", "g1", payload={"title": "First"}, actor="verify")
    k.save_projection_snapshot("goal")

    k.emit_event("WorkItemCreated", "work_item", "g2", payload={"title": "Second"}, actor="verify")
    k.emit_event("WorkItemUpdated", "work_item", "g1", payload={"progress": 0.5}, actor="verify")

    before = snapshot_work_items(db)
    replayed = k.rebuild("work_item")
    after = snapshot_work_items(db)

    if before != after:
        print("FAIL: goals differ after incremental rebuild", file=sys.stderr)
        return 1
    if replayed != 2:
        print(f"FAIL: expected 2 incremental events, got {replayed}", file=sys.stderr)
        return 1

    seq_before_export = read_checkpoint_seq(db, "goal")
    if seq_before_export is None:
        print("FAIL: goal checkpoint missing before export test", file=sys.stderr)
        return 1

    k.emit_event("WorkItemUpdated", "work_item", "g2", payload={"progress": 0.25}, actor="verify")
    k.snapshot()

    seq_after_export = read_checkpoint_seq(db, "goal")
    if seq_after_export is None:
        print("FAIL: goal checkpoint missing after export", file=sys.stderr)
        return 1
    if seq_after_export <= seq_before_export:
        print(
            f"FAIL: checkpoint last_applied_seq did not advance "
            f"({seq_before_export} -> {seq_after_export})",
            file=sys.stderr,
        )
        return 1

    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print(
        f"SNAPSHOT REBUILD PASSED — incremental replay {replayed} events; "
        f"export advanced checkpoint {seq_before_export} -> {seq_after_export}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

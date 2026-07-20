#!/usr/bin/env python
"""Verify incremental rebuild from projection checkpoint."""

from __future__ import annotations

from pathlib import Path

import sys
from typing import Any

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel


def snapshot_work_items(db: Any) -> list[dict]:
    with db.get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM work_items WHERE work_type = 'goal' ORDER BY id"
            ).fetchall()
        ]


def read_checkpoint_seq(db: Any, aggregate_type: str) -> int | None:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT last_applied_seq FROM projection_checkpoints WHERE aggregate_type = ?",
            (aggregate_type,),
        ).fetchone()
    return int(row["last_applied_seq"]) if row else None


def main() -> int:
    with ephemeral_kernel("verify_snapshot.db") as (db, k):
        k.emit_event(
            "WorkItemCreated", "work_item", "g1",
            payload={"title": "First", "work_type": "goal"}, actor="verify",
        )
        k.save_projection_snapshot("work_item")

        k.emit_event(
            "WorkItemCreated", "work_item", "g2",
            payload={"title": "Second", "work_type": "goal"}, actor="verify",
        )
        k.emit_event(
            "WorkItemUpdated", "work_item", "g1",
            payload={"progress": 0.5}, actor="verify",
        )

        before = snapshot_work_items(db)
        replayed = k.rebuild("work_item")
        after = snapshot_work_items(db)

        if before != after:
            print("FAIL: work_items differ after incremental rebuild", file=sys.stderr)
            return 1
        if replayed != 2:
            print(f"FAIL: expected 2 incremental events, got {replayed}", file=sys.stderr)
            return 1

        seq_before_export = read_checkpoint_seq(db, "work_item")
        if seq_before_export is None:
            print("FAIL: work_item checkpoint missing before export test", file=sys.stderr)
            return 1

        k.emit_event(
            "WorkItemUpdated", "work_item", "g2",
            payload={"progress": 0.25}, actor="verify",
        )
        k.save_projection_snapshots(("work_item",))

        seq_after_export = read_checkpoint_seq(db, "work_item")
        if seq_after_export is None:
            print("FAIL: work_item checkpoint missing after export", file=sys.stderr)
            return 1
        if seq_after_export <= seq_before_export:
            print(
                f"FAIL: checkpoint last_applied_seq did not advance "
                f"({seq_before_export} -> {seq_after_export})",
                file=sys.stderr,
            )
            return 1

    print(
        f"SNAPSHOT REBUILD PASSED — incremental replay {replayed} events; "
        f"checkpoint advanced {seq_before_export} -> {seq_after_export}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

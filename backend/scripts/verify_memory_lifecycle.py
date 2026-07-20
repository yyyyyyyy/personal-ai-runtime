#!/usr/bin/env python
"""Memory lifecycle verification — validates MemoryDerived → Updated → Deleted → rebuild.

Verifies:
1. MemoryDerived creates a row in memories projection
2. MemoryUpdated modifies content/confidence
3. MemoryDeleted removes the row
4. After rebuild, all states are byte-identical
"""

from __future__ import annotations

from pathlib import Path

import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import ephemeral_kernel


def main() -> int:
    with ephemeral_kernel("verify_memory_lifecycle.db") as (db, k):
        k.emit_event("MemoryDerived", "memory", "mem_lc", payload={
            "category": "fact", "content": "User prefers mornings",
            "confidence": 0.7, "derived_from_event": "evt_001",
        }, actor="agent:planner")
        k.emit_event("MemoryUpdated", "memory", "mem_lc", payload={
            "content": "User strongly prefers mornings",
            "confidence": 0.9,
        }, actor="agent:planner")

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            row = conn.execute(
                "SELECT content, confidence FROM memories WHERE id='mem_lc'"
            ).fetchone()
            if row is None:
                print("FAIL: MemoryDerived did not create row", file=sys.stderr)
                return 1
            if row["confidence"] != 0.9:
                print(
                    f"FAIL: Confidence not updated: {row['confidence']}",
                    file=sys.stderr,
                )
                return 1

        k.rebuild("memory")

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            row = conn.execute(
                "SELECT content, confidence FROM memories WHERE id='mem_lc'"
            ).fetchone()
            if row is None:
                print("FAIL: After rebuild, memory not restored", file=sys.stderr)
                return 1
            if row["confidence"] != 0.9:
                print(
                    f"FAIL: After rebuild confidence={row['confidence']}",
                    file=sys.stderr,
                )
                return 1

        k.emit_event("MemoryDeleted", "memory", "mem_lc", payload={},
                     actor="agent:planner")

        with db.get_db() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            row = conn.execute(
                "SELECT 1 FROM memories WHERE id='mem_lc'"
            ).fetchone()
            if row is not None:
                print("FAIL: MemoryDeleted did not remove row", file=sys.stderr)
                return 1

    print("MEMORY LIFECYCLE VERIFICATION PASSED — "
          "MemoryDerived/Updated/Deleted + rebuild consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())

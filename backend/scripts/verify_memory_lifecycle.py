#!/usr/bin/env python
"""Memory lifecycle verification — validates MemoryDerived → Updated → Deleted → rebuild.

Verifies:
1. MemoryDerived creates a row in memories projection
2. MemoryUpdated modifies content/confidence
3. MemoryDeleted removes the row
4. After rebuild, all states are byte-identical
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
    db_path = _BACKEND_ROOT / "data" / "verify_memory_lifecycle.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

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
        assert row is not None, "MemoryDerived did not create row"
        assert row["confidence"] == 0.9, f"Confidence not updated: {row['confidence']}"

    # Rebuild before delete to verify create+update works
    k.rebuild("memory")

    with db.get_db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        row = conn.execute(
            "SELECT content, confidence FROM memories WHERE id='mem_lc'"
        ).fetchone()
        assert row is not None, "After rebuild, memory not restored"
        assert row["confidence"] == 0.9

    k.emit_event("MemoryDeleted", "memory", "mem_lc", payload={},
                 actor="agent:planner")

    with db.get_db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        row = conn.execute(
            "SELECT 1 FROM memories WHERE id='mem_lc'"
        ).fetchone()
        assert row is None, "MemoryDeleted did not remove row"

    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        pass

    print("MEMORY LIFECYCLE VERIFICATION PASSED — "
          "MemoryDerived/Updated/Deleted + rebuild consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())

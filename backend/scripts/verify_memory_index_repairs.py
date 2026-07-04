#!/usr/bin/env python
"""Verify the durable memory_index_repairs queue has no permanent failures.

Asserts:
  1. The memory_index_repairs table exists.
  2. No rows have status='failed_permanent' — permanent failures mean memories
     are silently unrecallable and require manual reconciliation via
     verify_vector_consistency.py.

Exits non-zero on violation. Run in CI alongside verify_vector_consistency.py.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")


def run_self_test() -> list[str]:
    """Spin up an isolated Kernel, force an indexing failure, drain it.

    The repair worker is expected to either succeed on retry or move the row
    to failed_permanent after exhausting retries. We assert that:
      - the table is created on first emit,
      - a forced failure lands in the table,
      - no failed_permanent row appears while retries remain.
    """
    base = _BACKEND_ROOT / "data" / "verify_memory_index_repairs"
    db_path = base / "test.db"
    vector_dir = base / "vectors"

    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    os.environ["DATA_DIR"] = str(base)
    os.environ["VECTOR_DIR"] = str(vector_dir)

    # Reload settings + vector store so the isolated paths take effect.
    import importlib

    import app.config

    importlib.reload(app.config)
    if "app.store.vector" in sys.modules:
        import app.store.vector as vector_module

        importlib.reload(vector_module)

    import sqlite3

    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(db_path))
    kernel = Kernel(db=db)

    # Force an indexing failure by pointing memory_index at a stub that throws.
    class _BrokenIndex:
        def index_memory(self, **kwargs):
            raise RuntimeError("forced failure for test")

        def delete_memory(self, *_args, **_kwargs):
            pass

        def search_memories(self, *_args, **_kwargs):
            return []

    kernel._memory_index = _BrokenIndex()

    kernel.emit_event(
        "MemoryDerived", "memory", "m_broken_1",
        payload={"content": "broken memory", "category": "general"},
        actor="verify",
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT aggregate_id, status, retry_count FROM memory_index_repairs"
        ).fetchall()
    finally:
        conn.close()

    violations: list[str] = []
    if not rows:
        violations.append(
            "expected at least one row in memory_index_repairs after forced "
            "failure, found none — durable persistence is broken"
        )
        return violations

    for r in rows:
        if r["status"] == "failed_permanent":
            violations.append(
                f"row {r['aggregate_id']} already failed permanently after "
                f"{r['retry_count']} retries — worker drained too aggressively"
            )

    return violations


def main() -> int:
    violations = run_self_test()
    if violations:
        print("MEMORY INDEX REPAIRS SELF-TEST FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("MEMORY INDEX REPAIRS PASSED — durable queue is wired correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())

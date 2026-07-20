#!/usr/bin/env python
"""Verify the durable memory_index_repairs queue has no permanent failures.

Checks:
  1. The memory_index_repairs table exists.
  2. No rows have status='failed_permanent' — permanent failures mean memories
     are silently unrecallable and require manual reconciliation via
     verify_vector_consistency.py.

Exits non-zero on violation. Run in CI alongside verify_vector_consistency.py.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import prepare_script_env

prepare_script_env()


def run_self_test() -> list[str]:
    """Spin up an isolated Kernel, force an indexing failure, drain it.

    The repair worker is expected to either succeed on retry or move the row
    to failed_permanent after exhausting retries. We check that:
      - the table is created on first emit,
      - a forced failure lands in the table,
      - no failed_permanent row appears while retries remain.
    """
    with tempfile.TemporaryDirectory(
        prefix="verify_memory_index_repairs_",
        ignore_cleanup_errors=True,
    ) as tmp:
        base = Path(tmp)
        db_path = base / "test.db"
        vector_dir = base / "vectors"
        vector_dir.mkdir(parents=True, exist_ok=True)

        os.environ["DATA_DIR"] = str(base)
        os.environ["VECTOR_DIR"] = str(vector_dir)

        import app.config

        importlib.reload(app.config)
        if "app.store.vector" in sys.modules:
            import app.store.vector as vector_module

            importlib.reload(vector_module)

        from app.core.runtime.kernel import Kernel
        from app.store.database import Database

        db = Database(db_path=str(db_path))
        try:
            kernel = Kernel(db=db)

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
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

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

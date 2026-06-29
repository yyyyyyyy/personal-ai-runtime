#!/usr/bin/env python
"""Pattern Projection Replay Test — verifies Pattern as an Event Sourcing Primitive.

Uses an isolated tmp DB (CI-safe). Seeds a minimal PatternDetected event,
snapshots patterns, rebuilds, and asserts byte-identical state.

Success = Pattern is a First-Class Projection Primitive (same guarantees as State/Memory).
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel  # noqa: E402
from app.store.database import Database  # noqa: E402

MINIMAL_PATTERN = {
    "pattern_type": "time_distribution",
    "metric": "deep_work",
    "window_days": 14,
    "statistics": json.dumps({"proportion": 0.5, "sample_count": 3}),
    "evidence_chain": json.dumps(["evt_a2_001"]),
}


def _snapshot_patterns(kernel: Kernel) -> list[dict]:
    rows = kernel.query_state("patterns", limit=5000)
    return sorted(rows, key=lambda r: r["id"])


def _patterns_equal(a: list[dict], b: list[dict]) -> bool:
    if len(a) != len(b):
        print(f"  ERR: count mismatch — before={len(a)} after={len(b)}")
        return False
    for left, right in zip(a, b):
        if left["id"] != right["id"]:
            print(f"  ERR: id mismatch — {left['id']} vs {right['id']}")
            return False
        for col in ("pattern_type", "metric", "window_days", "statistics", "evidence_chain"):
            if left.get(col) != right.get(col):
                print(f"  ERR: column {col} mismatch on {left['id']}")
                return False
    return True


def _seed_minimal_pattern(kernel: Kernel) -> None:
    kernel.emit_event(
        "PatternDetected",
        "pattern",
        "pat_verify_a2",
        payload=MINIMAL_PATTERN,
        actor="verify",
    )


def main() -> int:
    print("=== Pattern Projection Replay Test ===")

    tmp_dir = Path(tempfile.mkdtemp(prefix="verify_pattern_"))
    db_path = tmp_dir / "test.db"
    try:
        kernel = Kernel(db=Database(db_path=str(db_path)))

        existing = _snapshot_patterns(kernel)
        if not existing:
            print("  0. Seeding minimal PatternDetected event (isolated DB)")
            _seed_minimal_pattern(kernel)

        before = _snapshot_patterns(kernel)
        print(f"  1. Snapshot before rebuild: {len(before)} rows")

        count = kernel.rebuild("pattern")
        print(f"  2. kernel.rebuild('pattern') replayed {count} events")

        after = _snapshot_patterns(kernel)
        print(f"  3. Snapshot after rebuild: {len(after)} rows")

        if _patterns_equal(before, after):
            print("  4. PASS — patterns table is fully reconstructible from Event Log")
            return 0

        for left, right in zip(before, after):
            if left != right:
                print("\n  First diff:")
                print(f"    before: {json.dumps(left, indent=4)}")
                print(f"    after:  {json.dumps(right, indent=4)}")
                break
        print("\n  4. FAIL — rebuild did not produce identical state")
        return 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

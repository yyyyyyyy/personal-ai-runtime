#!/usr/bin/env python
"""Phase 1B Pipeline Verification — Evidence → Pattern → Belief.

Uses an isolated tmp DB (CI-safe). Seeds synthetic PatternDetected + BeliefFormed
events and verifies projection materialization and rebuild.
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

from app.core.belief.belief_engine import ReflectionContext  # noqa: E402
from app.core.runtime.kernel import Kernel  # noqa: E402
from app.store.database import Database  # noqa: E402


def _count_beliefs(kernel: Kernel) -> int:
    rows = kernel.query_state("memories", category="belief", confidence_gt=0.1, limit=500)
    return len(rows)


def _seed_minimal_pattern(kernel: Kernel, pattern_id: str = "pat_test_verify") -> None:
    kernel.emit_event(
        type="PatternDetected",
        aggregate_type="pattern",
        aggregate_id=pattern_id,
        payload={
            "pattern_type": "time_distribution",
            "metric": "deep_work",
            "window_days": 14,
            "statistics": json.dumps({
                "time_of_day": "morning",
                "proportion": 0.78,
                "duration_minutes": 780,
                "sample_count": 15,
            }),
            "evidence_chain": json.dumps(["evt_test_001", "evt_test_002"]),
        },
        actor="test",
    )


def main() -> int:
    print("=== Phase 1B Pipeline Verification ===")

    tmp_dir = Path(tempfile.mkdtemp(prefix="verify_belief_"))
    db_path = tmp_dir / "test.db"
    try:
        kernel = Kernel(db=Database(db_path=str(db_path)))

        patterns = kernel.query_state("patterns", limit=20)
        if not patterns:
            print("  0. Seeding minimal PatternDetected event (isolated DB)")
            _seed_minimal_pattern(kernel)
            patterns = kernel.query_state("patterns", limit=20)

        print(f"  1. Patterns available: {len(patterns)}")
        for p in patterns[:3]:
            stats = json.loads(p["statistics"])
            print(f"     - [{p['pattern_type']}] {p['metric']}: {json.dumps(stats, ensure_ascii=False)[:80]}")

        goals = kernel.query_state("goals", status="active", limit=10)
        memories = kernel.query_state("memories", confidence_gt=0.3, limit=10)
        ctx = ReflectionContext(patterns=patterns, goals=goals, memories=memories)

        assert hasattr(ctx, "patterns"), "ReflectionContext must have patterns field"
        assert hasattr(ctx, "goals"), "ReflectionContext must have goals field"
        assert hasattr(ctx, "memories"), "ReflectionContext must have memories field"
        assert not hasattr(ctx, "events"), "ReflectionContext MUST NOT have events field"
        print(
            f"  2. PASS: ReflectionContext consumes projections only "
            f"(patterns={len(patterns)}, goals={len(goals)}, memories={len(memories)})"
        )

        test_pid = "pat_test_verify"
        belief_id = "blf_test_verify"
        kernel.emit_event(
            type="BeliefFormed",
            aggregate_type="memory",
            aggregate_id=belief_id,
            payload={
                "category": "belief",
                "content": "用户上午效率最高",
                "confidence": 0.72,
                "belief_type": "belief",
                "source": "reflection_test",
                "evidence_chain": json.dumps({"patterns": [test_pid]}),
            },
            actor="test",
        )

        belief_row = kernel.query_state("memories", id=belief_id, limit=1)
        assert len(belief_row) == 1, f"BeliefFormed should materialize in memories table, got {len(belief_row)}"
        b = belief_row[0]
        assert b["category"] == "belief", f"Expected category=belief, got {b['category']}"
        assert b["content"] == "用户上午效率最高"
        assert float(b["confidence"]) >= 0.5
        print(f"  3. PASS: BeliefFormed → memories table materialized (confidence={b['confidence']})")

        all_beliefs = kernel.query_state("memories", category="belief", limit=500)
        test_belief = [m for m in all_beliefs if m["id"] == belief_id]
        assert len(test_belief) == 1, f"Belief {belief_id} should be queryable as category=belief"
        print(
            f"  4. PASS: Belief queryable via query_state('memories', category='belief') "
            f"(total={len(all_beliefs)})"
        )

        before_rebuild = _count_beliefs(kernel)
        count = kernel.rebuild("memory")
        after_rebuild = _count_beliefs(kernel)
        assert after_rebuild == before_rebuild, (
            f"Rebuild should preserve belief count: {before_rebuild} != {after_rebuild}"
        )
        print(
            f"  5. PASS: kernel.rebuild('memory') preserved {after_rebuild} beliefs "
            f"({count} events replayed)"
        )

        print("\n=== All Phase 1B tests passed ===")
        print("Pipeline: Pattern → Projection → BeliefFormed → memories")
        print("Constraint: Reflection consumes projections only (no raw events)")
        print("Rebuild: Belief is reconstructible from Event Log")
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

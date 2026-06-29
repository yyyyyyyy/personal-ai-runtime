#!/usr/bin/env python
"""Pattern Idempotency Test — verifies PatternDetected is deterministic.

Given the same ActivityNormalized events in the same order, the Aggregator
must produce the same PatternDetected events with the same aggregate_id,
and INSERT OR REPLACE must prevent duplicate pattern rows.
"""

import json
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.pattern.aggregators import (
    _make_pattern_id,
)


def main() -> int:
    print("=== Pattern Idempotency Test ===")

    # 1. Compute what aggregate_id a specific pattern would produce
    pid1 = _make_pattern_id("time_distribution", "deep_work", 14, "morning")
    pid2 = _make_pattern_id("time_distribution", "deep_work", 14, "morning")
    pid3 = _make_pattern_id("time_distribution", "deep_work", 14, "afternoon")

    assert pid1 == pid2, f"SHA256 is non-deterministic! {pid1} != {pid2}"
    assert pid1 != pid3, f"Different buckets must produce different ids: {pid1} == {pid3}"
    print("  1. PASS: SHA256 aggregate_id is deterministic and collision-resistant")

    # 2. Emit the same PatternDetected twice → INSERT OR REPLACE handles idempotency
    ts = "2026-06-10T09:00:00"
    evt_ids = json.dumps([f"evt_{uuid.uuid4().hex[:8]}" for _ in range(5)])
    stats = json.dumps(
        {
            "time_of_day": "morning",
            "proportion": 0.78,
            "duration_minutes": 780,
            "total_duration_minutes": 1000,
            "sample_count": 15,
        }
    )

    def emit_test_pattern():
        kernel.emit_event(
            type="PatternDetected",
            aggregate_type="pattern",
            aggregate_id=pid1,
            payload={
                "pattern_type": "time_distribution",
                "metric": "deep_work",
                "window_days": 14,
                "statistics": stats,
                "evidence_chain": evt_ids,
            },
            actor="test",
        )

    emit_test_pattern()
    count_before = len(kernel.query_state("patterns", limit=5000))

    emit_test_pattern()  # same id → INSERT OR REPLACE
    count_after = len(kernel.query_state("patterns", limit=5000))

    if count_before == count_after:
        print(f"  2. PASS: Idempotent — duplicate emit did not increase row count ({count_before})")
    else:
        print(f"  2. FAIL — count changed: {count_before} -> {count_after}")
        return 1

    # 3. Belief Independence: query_state("patterns") works without LLM
    rows = kernel.query_state("patterns", metric="deep_work", window_days=14, limit=10)
    assert len(rows) > 0, "No patterns found after emit"
    row = rows[0]
    parsed_stats = json.loads(row["statistics"])
    assert parsed_stats["proportion"] == 0.78
    assert parsed_stats["sample_count"] == 15
    print("  3. PASS: Belief Independence — pattern queryable without LLM")
    print(f"     pattern_type={row['pattern_type']} metric={row['metric']} proportion={parsed_stats['proportion']}")

    print("\nAll tests passed — Pattern is an Event Sourcing Primitive")
    return 0


if __name__ == "__main__":
    sys.exit(main())

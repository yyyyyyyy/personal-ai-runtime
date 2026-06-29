#!/usr/bin/env python
"""Belief Lifecycle Tracker — survival, formation, revocation, strengthening stats.

Measures cognitive stability: how long do beliefs survive before being
contradicted?  What fraction are strengthened vs revoked?

Outputs a report suitable for Phase 1B.5 observation windows (daily/weekly).

Per Cognitive Architecture:
    Belief survival is a proxy for cognitive quality.
    High survival → patterns are stable, reflection is accurate.
    High revocation → contradictions are frequent, patterns may be noisy.
"""

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.runtime.kernel_instance import kernel


def _parse_datetime(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, OSError):
        return datetime.min


def _days_between(start: str, end: str) -> int:
    try:
        dt1 = datetime.fromisoformat(start)
        dt2 = datetime.fromisoformat(end)
        return (dt2 - dt1).days
    except (ValueError, OSError):
        return 0


def main() -> int:
    print("=== Belief Lifecycle Report ===")

    now = datetime.utcnow()

    # Read all belief-related events from event_log
    formed_events = kernel.read_events(
        type="BeliefFormed", order="asc", limit=5000
    )
    strengthened_events = kernel.read_events(
        type="BeliefStrengthened", order="asc", limit=5000
    )
    revoked_events = kernel.read_events(
        type="BeliefRevoked", order="asc", limit=5000
    )

    if not formed_events:
        print("\n  No BeliefFormed events in event_log.")
        print("  Run the system with patterns + belief_reflection cron first.")
        return 0

    # Index events by belief_id
    formed_by_id: dict[str, dict] = {}
    for e in formed_events:
        formed_by_id[e.aggregate_id] = {
            "formed_at": e.ts,
            "confidence": (e.payload or {}).get("confidence", 0.5),
            "content": (e.payload or {}).get("content", "")[:60],
        }

    strengthened_by_id: dict[str, list[str]] = defaultdict(list)
    for e in strengthened_events:
        strengthened_by_id[e.aggregate_id].append(e.ts)

    revoked_at: dict[str, str] = {}
    for e in revoked_events:
        revoked_at[e.aggregate_id] = e.ts

    # --- Compute per-belief metrics ---
    active_count = 0
    revoked_count = 0
    strengthened_count = 0
    survival_days_list: list[int] = []
    current_survival_days_list: list[int] = []

    for belief_id, info in formed_by_id.items():
        formed_ts = info["formed_at"]
        is_revoked = belief_id in revoked_at
        has_strengthened = belief_id in strengthened_by_id

        if is_revoked:
            revoked_count += 1
            days = _days_between(formed_ts, revoked_at[belief_id])
            survival_days_list.append(max(days, 0))
        else:
            active_count += 1
            days = _days_between(formed_ts, now.isoformat())
            current_survival_days_list.append(max(days, 0))

        if has_strengthened:
            strengthened_count += 1

    total = len(formed_by_id)

    # --- Print report ---
    print(f"\n  Snapshot: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Total beliefs formed:     {total}")
    print(f"  Currently active:         {active_count}")
    print(f"  Revoked:                  {revoked_count}")
    print(f"  Strengthened at least 1x: {strengthened_count}")

    revocation_rate = revoked_count / total if total > 0 else 0
    strengthen_rate = strengthened_count / total if total > 0 else 0
    print(f"  Revocation rate:          {revocation_rate:.1%}")
    print(f"  Strengthen rate:          {strengthen_rate:.1%}")

    if survival_days_list:
        avg_revoked = sum(survival_days_list) / len(survival_days_list)
        min_r = min(survival_days_list)
        max_r = max(survival_days_list)
        print("  Survival (revoked):")
        print(f"    avg: {avg_revoked:.1f}d  min: {min_r}d  max: {max_r}d  count: {len(survival_days_list)}")
    else:
        print("  Survival (revoked):       none revoked yet")

    if current_survival_days_list:
        avg_active = sum(current_survival_days_list) / len(current_survival_days_list)
        min_a = min(current_survival_days_list)
        max_a = max(current_survival_days_list)
        print("  Survival (active so far):")
        print(f"    avg: {avg_active:.1f}d  min: {min_a}d  max: {max_a}d  count: {len(current_survival_days_list)}")

    # --- Per-belief detail (top 10 by age) ---
    print("\n  --- Top 10 beliefs by age ---")
    # Sort: revoked first (by survival days), then active by current age
    all_beliefs = []
    for belief_id, info in formed_by_id.items():
        is_revoked = belief_id in revoked_at
        survival = (
            _days_between(info["formed_at"], revoked_at[belief_id])
            if is_revoked
            else _days_between(info["formed_at"], now.isoformat())
        )
        all_beliefs.append((survival, belief_id, info, is_revoked))
    all_beliefs.sort(key=lambda x: x[0], reverse=True)

    for survival, bid, info, is_revoked in all_beliefs[:10]:
        status = "REVOKED" if is_revoked else "active"
        age_tag = f"survived {survival}d" if is_revoked else f"age {survival}d"
        print(
            f"  [{bid[:12]}...] "
            f"({status} {age_tag} conf={info['confidence']:.2f}) "
            f"\"{info['content']}\""
        )

    # --- Quality signals ---
    print("\n  --- Quality Signals ---")
    issues = []

    if total > 0 and revocation_rate > 0.3:
        issues.append(f"High revocation rate ({revocation_rate:.0%}): patterns may be too noisy")

    if total > 0 and strengthen_rate > 0.3 and revocation_rate > 0:
        issues.append(
            f"Mixed signals: {strengthen_rate:.0%} strengthened but some revoked. "
            "Beliefs are evolving — this is expected early-phase behavior."
        )

    if total > 0 and revocation_rate == 0 and total >= 5:
        issues.append(
            "Zero revocations with 5+ beliefs: either patterns are very stable, "
            "or contradictions are not being detected."
        )

    if strengthened_count == 0 and total >= 5:
        issues.append(
            "No beliefs strengthened: reflection may be producing one-shot beliefs "
            "without tracking whether subsequent patterns confirm them."
        )

    if not issues:
        print("  No quality concerns detected (may be too early to tell).")
    else:
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")

    print(f"\n{'='*50}")
    print("  Belief Lifecycle Report complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

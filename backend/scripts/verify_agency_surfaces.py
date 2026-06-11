#!/usr/bin/env python
"""Agency surface lint — G5 static + runtime ranking guard."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.agency_gate import (
    rank_active_goals_for_brief,
    rank_goals_for_agency,
)
from app.core.runtime.kernel import Kernel
from app.core.runtime.projection.agency_lint import lint_all_agency_surfaces
from app.store.database import Database


def _verify_runtime_g5() -> list[str]:
  violations: list[str] = []
  db_path = _BACKEND_ROOT / "data" / "verify_agency_g5.db"
  db_path.parent.mkdir(parents=True, exist_ok=True)
  db = Database(db_path=str(db_path))
  k = Kernel(db=db)

  import app.core.runtime.kernel_instance as ki
  import app.store.database as db_mod

  ki.kernel = k
  db_mod.db = db

  with db.get_db() as conn:
      conn.execute("DELETE FROM notifications WHERE type = 'brief'")
      conn.execute("DELETE FROM goals")

  g_low = "goal-low"
  g_high = "goal-high"
  k.emit_event(
      "GoalCreated", "goal", g_low,
      payload={"title": "低优先", "importance": 0.2, "urgency": 0.2, "status": "active"},
      actor="user",
  )
  k.emit_event(
      "GoalCreated", "goal", g_high,
      payload={"title": "高优先", "importance": 0.9, "urgency": 0.9, "status": "active"},
      actor="user",
  )

  proposed_id = "blf-agency-proposed"
  k.emit_event(
      "BeliefFormed", "memory", proposed_id,
      payload={
          "content": "你必须优先创业",
          "confidence": 0.99,
          "category": "belief",
      },
      actor="system",
  )
  proposed = k.query_state("memories", id=proposed_id)[0]
  proposed["linked_goal_id"] = g_low

  ranked = rank_goals_for_agency(
      k.query_state("goals", status="active"),
      meaning_boosts=[proposed],
  )
  if not ranked or ranked[0].get("id") != g_high:
      violations.append(
          f"G5.runtime: proposed meaning boosted ranking: first={ranked[0].get('id') if ranked else None}"
      )

  brief_ranked = rank_active_goals_for_brief(k, limit=3)
  if not brief_ranked or brief_ranked[0].get("title") != "高优先":
      violations.append(
          f"G5.brief: expected 高优先 first, got "
          f"{brief_ranked[0].get('title') if brief_ranked else None!r}"
      )

  return violations


def main() -> int:
    issues = lint_all_agency_surfaces()
    failures = [i for i in issues if i.startswith("FAIL:")]
    warnings = [i for i in issues if i.startswith("WARN:")]

    for w in warnings:
        print(f"  note: {w}", file=sys.stderr)

    failures.extend(_verify_runtime_g5())

    if failures:
        print("AGENCY SURFACE VERIFICATION FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("AGENCY SURFACE VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

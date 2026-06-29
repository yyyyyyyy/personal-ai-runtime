#!/usr/bin/env python
"""Belief Quality Evaluation — five quality gates for Phase 1B beliefs.

Per Cognitive Architecture quality constraints:
  1. Traceability   — every belief references >= 1 pattern
  2. Non-Restatement — belief must not just repeat pattern statistics
  3. Novelty         — belief must contain interpretation, not just translation
  4. Revocability    — BeliefRevoked → confidence=0, still queryable
  5. Actionability   — belief should imply a potential action (final goal)

These are heuristic checks — not a substitute for human review, but a CI gate
that prevents obvious degeneracy in the Reflection pipeline.
"""

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.runtime.kernel_instance import kernel


def _parse_evidence_chain(derived_from_event: str) -> list[str]:
    """Extract pattern IDs from derived_from_event JSON."""
    try:
        data = json.loads(derived_from_event)
        return data.get("patterns", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


def _has_statistical_restatement(content: str) -> bool:
    """Heuristic: detect if belief content is just restating statistics.

    Examples of restatement (BAD):
      "上午深度工作占比78%"
      "过去14天睡眠时间平均6.2小时"

    These are patterns, not beliefs.
    """
    # Contains a percentage + the word "占比" or "平均"
    if re.search(r"\d{1,3}%", content) and any(w in content for w in ("占比", "平均", "比例")):
        return True
    # Just a number + unit statement without interpretation
    if re.match(r"^[\u4e00-\u9fff\w]+\d+[\u4e00-\u9fff]*[%倍个次]", content) and len(content) < 20:
        return True
    return False


def _has_interpretation(content: str) -> bool:
    """Heuristic: detect whether content goes beyond data restatement.

    Interpretation markers (Chinese):
      "可能是" "或许是" "倾向于" "最佳" "黄金" "窗口"
      "影响" "导致" "关联" "趋势"
    """
    markers = (
        "可能", "或许", "倾向于", "最佳", "黄金", "窗口",
        "影响", "导致", "关联", "趋势", "建议", "注意",
        "正在", "持续", "逐渐", "下降", "上升",
    )
    return any(m in content for m in markers)


def _has_actionable_language(content: str) -> bool:
    """Heuristic: detect whether belief suggests a behavioral change.

    Actionable markers (Chinese):
      "建议" "避免" "优先" "尝试" "考虑" "调整"
      "安排" "分配" "预留" "减少" "增加" "改为"

    High-value beliefs translate pattern into decision guidance:
      GOOD: "上午可能是黄金创作窗口，建议避免在9:00-11:30安排会议"
      BAD:  "用户上午效率最高"  (interpretation only, no action)
    """
    action_markers = (
        "建议", "避免", "优先", "尝试", "考虑", "调整",
        "安排", "分配", "预留", "减少", "增加", "改为",
        "推迟", "提前", "集中", "分散", "替换", "取消",
    )
    return any(m in content for m in action_markers)


def _format_belief_for_report(belief: dict, patterns_found: int, actionable: bool | None = None) -> str:
    tag = ""
    if actionable is True:
        tag = " [actionable]"
    elif actionable is False:
        tag = " [no-action]"
    return (
        f"  [{belief['id'][:12]}...] "
        f"(conf={belief.get('confidence', 0):.2f} pats={patterns_found})"
        f"{tag}"
        f" \"{belief.get('content', '')[:80]}\""
    )


def main() -> int:
    print("=== Belief Quality Evaluation ===")

    beliefs = kernel.query_state("memories", category="belief", limit=500)

    if not beliefs:
        print("\n  SKIP: no beliefs to evaluate.  "
              "Run the system with patterns + belief_reflection cron first.")
        return 0

    print(f"\n  Total beliefs found: {len(beliefs)}")

    violations = 0
    warnings = 0

    # ---- Gate 1: Traceability ----
    print("\n--- Gate 1: Traceability (each belief references >= 1 pattern) ---")
    for b in beliefs:
        chain = _parse_evidence_chain(b.get("derived_from_event", ""))
        if len(chain) == 0:
            violations += 1
            print(f"  FAIL: {_format_belief_for_report(b, 0)} — no pattern references")
        else:
            print(f"  PASS: {_format_belief_for_report(b, len(chain))}")

    # ---- Gate 2: Non-Restatement ----
    print("\n--- Gate 2: Non-Restatement (belief != pattern translation) ---")
    for b in beliefs:
        if _has_statistical_restatement(b.get("content", "")):
            warnings += 1
            print(f"  WARN: {_format_belief_for_report(b, 0)} — appears to restate statistics")
        else:
            print("  PASS: no statistical restatement detected")

    # ---- Gate 3: Novelty (interpretation over translation) ----
    print("\n--- Gate 3: Novelty (interpretation, not translation) ---")
    for b in beliefs:
        content = b.get("content", "")
        if not _has_interpretation(content):
            warnings += 1
            print(f"  WARN: {_format_belief_for_report(b, 0)} — lacks interpretation markers")
        else:
            print("  PASS: contains interpretation")

    # ---- Gate 4: Revocability ----
    print("\n--- Gate 4: Revocability (BeliefRevoked → confidence=0, still queryable) ---")
    # Emit a test BeliefFormed, then BeliefRevoked, verify it's still queryable
    test_id = "blf_quality_revoke_test"
    kernel.emit_event(
        type="BeliefFormed",
        aggregate_type="memory",
        aggregate_id=test_id,
        payload={
            "category": "belief",
            "content": "测试信念-将被撤销",
            "confidence": 0.5,
            "source": "quality_test",
            "derived_from_event": json.dumps({"patterns": ["pat_test"]}),
        },
        actor="test",
    )

    kernel.emit_event(
        type="BeliefRevoked",
        aggregate_type="memory",
        aggregate_id=test_id,
        payload={"reason": "quality_test"},
        actor="test",
    )

    revoked = kernel.query_state("memories", id=test_id, limit=1)
    if len(revoked) == 0:
        violations += 1
        print("  FAIL: revoked belief was physically deleted (should be retained)")
    else:
        r = revoked[0]
        conf = float(r.get("confidence", -1))
        status = r.get("status", "")
        if conf == 0.0 and status == "revoked":
            print(f"  PASS: revoked belief retained (confidence={conf}, status={status})")
        else:
            violations += 1
            print(f"  FAIL: revoked belief has unexpected state (confidence={conf}, status={status})")

    # ---- Gate 5: Actionability ----
    print("\n--- Gate 5: Actionability (belief implies behavior change) ---")
    actionable_count = 0
    for b in beliefs:
        if b.get("status") == "revoked":
            continue
        content = b.get("content", "")
        if _has_actionable_language(content):
            actionable_count += 1
            print(f"  PASS: {_format_belief_for_report(b, 0, actionable=True)}")
        else:
            print(f"  WARN: {_format_belief_for_report(b, 0, actionable=False)} — no actionable language")
    if len([b for b in beliefs if b.get("status") != "revoked"]) > 0 and actionable_count == 0:
        warnings += 1
    print(f"  Actionable beliefs: {actionable_count}/{len(beliefs)}")

    # ---- Summary ----
    print(f"\n{'='*50}")
    print(f"  Violations: {violations}  Warnings: {warnings}  Total: {len(beliefs)}")

    if violations > 0:
        print(f"\n  FAIL: {violations} quality gate violations detected")
        return 1
    elif warnings > 0:
        print(f"\n  PASS with {warnings} warnings — manual review recommended")
        return 0
    else:
        print("\n  PASS — all beliefs meet quality gates")
        return 0


if __name__ == "__main__":
    sys.exit(main())

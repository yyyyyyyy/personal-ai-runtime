"""Tension Detection — discovers unresolved tensions between Meaning objects.

Tensions are emitted as Claim subtype events (TensionProposed), reusing
claim_authority.py's epistemic state machine (proposed → ratified/rejected/...).
No new Runtime Primitive is introduced.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.runtime.kernel_instance import kernel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_tension(
    tension_type: str,
    left_ref: dict[str, Any],
    right_ref: dict[str, Any],
    description: str,
    *,
    actor: str = "system",
) -> str:
    """Emit a TensionProposed event (Claim subtype). Returns the claim ID."""
    tension_id = f"tns_{uuid.uuid4().hex[:12]}"
    kernel.emit_event(
        "TensionProposed",
        "claim",
        tension_id,
        payload={
            "claim_type": "tension",
            "tension_type": tension_type,
            "left_ref": left_ref,
            "right_ref": right_ref,
            "description": description,
            "claim_status": "proposed",
        },
        actor=actor,
    )
    return tension_id


# ---------------------------------------------------------------------------
# Detection rules
# ---------------------------------------------------------------------------


def detect_belief_behavior_gap(
    *,
    lookback_days: int = 7,
    confidence_threshold: float = 0.5,
) -> list[str]:
    """Detect gaps between ratified Beliefs and recent behavioral events.

    A gap exists when a memory with origin=claim and claim_status=ratified
    asserts a pattern (e.g. "重视健康") but recent events suggest contrary
    behavior (e.g. consecutive late nights).
    """
    found: list[str] = []
    memories = kernel.query_state(
        "memories", origin="claim", claim_status="ratified", limit=200
    )
    since = (_now()[:19] if lookback_days < 0 else
             (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()[:19])

    recent = kernel.read_events(since_ts=since, limit=2000, order="asc")

    for m in memories:
        if float(m.get("confidence", 0)) < confidence_threshold:
            continue
        content = m.get("content", "")
        _id = m.get("id", "")

        # Simple heuristic: check if memory asserts a health/family/work value,
        # then look for contradicting events in recent window
        if _check_health_belief(content) and _find_sleep_deprivation(recent):
            found.append(_emit_tension(
                "belief_behavior_gap",
                left_ref={"type": "belief", "id": _id},
                right_ref={"type": "events", "count": _count_sleep_deprivation(recent)},
                description=f"信念 '{content[:50]}' 与近期睡眠不足事件存在张力",
            ))
        if _check_family_belief(content) and _find_family_absence(recent):
            found.append(_emit_tension(
                "belief_behavior_gap",
                left_ref={"type": "belief", "id": _id},
                right_ref={"type": "events", "count": _count_family_absence(recent)},
                description=f"信念 '{content[:50]}' 与近期家庭活动缺失存在张力",
            ))

    return found


def detect_trajectory_neglect(*, inactive_days: int = 14) -> list[str]:
    """Detect trajectories with no new TrajectoryLinked events in N days."""
    found: list[str] = []
    trajectories = kernel.list_trajectories()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=inactive_days)).isoformat()[:19]

    for t in trajectories:
        tid = t.get("id")
        if not tid or t.get("status") != "active":
            continue
        try:
            data = kernel.query_trajectory(tid)
            if not data:
                continue
            links = data.get("links", [])
            recent = [lnk for lnk in links
                      if lnk.get("linked_at") and lnk["linked_at"] > cutoff]
            if not recent and links:
                found.append(_emit_tension(
                    "trajectory_neglect",
                    left_ref={"type": "trajectory", "id": tid},
                    right_ref={"type": "threshold", "inactive_days": inactive_days},
                    description=f"轨迹 '{t.get('description', tid)[:50]}' 已 {inactive_days} 天无新活动",
                ))
        except Exception:
            continue
    return found


def detect_intent_action_gap(*, max_deferrals: int = 3) -> list[str]:
    """Detect goals that have been deferred repeatedly."""
    found: list[str] = []
    goals = kernel.query_state("goals", status="active", limit=100)
    events = kernel.read_events(type="GoalUpdated", limit=2000, order="desc")

    for g in goals:
        gid = g.get("id")
        gtitle = str(g.get("title", gid or ""))
        updates = [e for e in events if e.aggregate_id == gid]
        # Count updates where deadline was pushed back
        defer_count = sum(
            1 for e in updates
            if (e.payload or {}).get("deadline")
            and (e.payload or {}).get("previous_deadline")
        )
        if defer_count >= max_deferrals:
            found.append(_emit_tension(
                "intent_action_gap",
                left_ref={"type": "goal", "id": gid or ""},
                right_ref={"type": "deferrals", "count": defer_count},
                description=f"目标 '{gtitle[:50]}' 已推迟 {defer_count} 次",
            ))
    return found


def detect_competing_dominance(*, ratio_threshold: float = 3.0) -> list[str]:
    """Detect competing trajectory pairs where one side dominates (>ratio)."""
    found: list[str] = []
    trajectories = kernel.list_trajectories()

    for t in trajectories:
        tid: str | None = t.get("id")
        if not tid:
            continue
        competing = t.get("competing_with") or []
        for other_id in competing:
            try:
                a_data = kernel.query_trajectory(tid)
                b_data = kernel.query_trajectory(str(other_id))
                if not a_data or not b_data:
                    continue
                a_count = len(a_data.get("links", []))
                b_count = len(b_data.get("links", []))
                if a_count > 0 and b_count > 0:
                    ratio = max(a_count, b_count) / min(a_count, b_count)
                    if ratio >= ratio_threshold:
                        dom = tid if a_count > b_count else other_id
                        sub = other_id if a_count > b_count else tid
                        found.append(_emit_tension(
                            "competing_dominance",
                            left_ref={"type": "trajectory", "id": dom, "link_count": max(a_count, b_count)},
                            right_ref={"type": "trajectory", "id": sub, "link_count": min(a_count, b_count)},
                            description=f"竞争轨迹对 {tid}/{other_id} 链接比 {ratio:.1f}:1",
                        ))
            except Exception:
                continue
    return found


def run_tension_detection() -> dict[str, int]:
    """Run all 4 detection rules and return counts per type."""
    result = {
        "belief_behavior_gap": len(detect_belief_behavior_gap()),
        "trajectory_neglect": len(detect_trajectory_neglect()),
        "intent_action_gap": len(detect_intent_action_gap()),
        "competing_dominance": len(detect_competing_dominance()),
    }
    return result


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

_HEALTH_KEYWORDS = {"健康", "睡眠", "运动", "锻炼", "身体", "健身", "熬夜", "作息"}
_FAMILY_KEYWORDS = {"家庭", "家人", "亲人", "陪伴", "孩子", "父母", "妻", "夫", "归属"}


def _check_health_belief(content: str) -> bool:
    return any(kw in content for kw in _HEALTH_KEYWORDS)


def _check_family_belief(content: str) -> bool:
    return any(kw in content for kw in _FAMILY_KEYWORDS)


def _find_sleep_deprivation(events: list) -> bool:
    return _count_sleep_deprivation(events) >= 3


def _count_sleep_deprivation(events: list) -> int:
    count = 0
    for e in events:
        p = e.payload or {}
        if isinstance(p, dict):
            content = str(p.get("content", "") or p.get("summary", ""))
            if any(kw in content for kw in {"睡眠", "熬夜", "失眠", "深夜", "凌晨"}):
                count += 1
    return count


def _find_family_absence(events: list) -> bool:
    return _count_family_absence(events) == 0


def _count_family_absence(events: list) -> int:
    return sum(1 for e in events
               if any(kw in str(e.payload or {})
                      for kw in _FAMILY_KEYWORDS))

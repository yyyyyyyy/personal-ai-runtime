"""Agency runtime gate — Constitution G5.

Unratified Meaning (Claim / Trajectory edge / Belief) MUST NOT influence
Agency projection ranking. Goals remain commissive-only inputs.
"""

from __future__ import annotations

from typing import Any

from app.core.runtime.claim_authority import can_drive_agency

_RATIFIED = frozenset({"ratified"})


def may_influence_agency_ranking(row: dict[str, Any]) -> bool:
    """Whether a Meaning row may affect Agency ranking (not presentation)."""
    origin = row.get("origin")
    if origin == "self_report":
        return False
    if origin == "claim":
        return can_drive_agency(row)
    belief_type = row.get("belief_type") or row.get("category")
    if belief_type == "belief" or origin == "belief":
        status = row.get("claim_status") or "proposed"
        return status in _RATIFIED
    return False


def filter_meaning_for_agency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only Meaning rows eligible to influence Agency."""
    return [r for r in rows if may_influence_agency_ranking(r)]


def rank_goals_for_agency(
    goals: list[dict[str, Any]],
    *,
    meaning_boosts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Sort goals by commissive fields only; optional boosts from ratified Meaning."""

    allowed_boosts = filter_meaning_for_agency(meaning_boosts or [])
    boost_goal_ids: set[str] = set()
    for b in allowed_boosts:
        linked = b.get("linked_goal_id")
        if linked:
            boost_goal_ids.add(str(linked))
        elif b.get("id"):
            boost_goal_ids.add(str(b["id"]))

    def sort_key(g: dict[str, Any]) -> tuple[float, float, str]:
        importance = float(g.get("importance") or 0)
        urgency = float(g.get("urgency") or 0)
        boost = 0.01 if g.get("id") in boost_goal_ids else 0.0
        return (-importance - boost, -urgency, g.get("deadline") or "")

    return sorted(goals, key=sort_key)


def rank_active_goals_for_brief(kernel, *, limit: int = 5) -> list[dict[str, Any]]:
    """G5-aware goal ranking for morning brief (Meaning inputs isolated here)."""
    goals = kernel.query_state("goals", status="active", limit=50)
    boosts = kernel.query_state("memories", origin="claim", limit=500)
    return rank_goals_for_agency(goals, meaning_boosts=boosts)[:limit]

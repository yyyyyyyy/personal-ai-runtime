"""Agency gate G5 runtime tests."""

from app.core.runtime.agency_gate import may_influence_agency_ranking, rank_goals_for_agency


def test_proposed_claim_cannot_boost_ranking():
    goals = [
        {"id": "g1", "title": "A", "importance": 0.3, "urgency": 0.3},
        {"id": "g2", "title": "B", "importance": 0.8, "urgency": 0.8},
    ]
    proposed = {
        "id": "c1",
        "origin": "claim",
        "claim_status": "proposed",
        "confidence": 0.9,
        "linked_goal_id": "g1",
    }
    ranked = rank_goals_for_agency(goals, meaning_boosts=[proposed])
    assert ranked[0]["id"] == "g2"
    assert not may_influence_agency_ranking(proposed)


def test_ratified_claim_may_boost_linked_goal():
    goals = [
        {"id": "g1", "title": "A", "importance": 0.5, "urgency": 0.5},
        {"id": "g2", "title": "B", "importance": 0.5, "urgency": 0.5},
    ]
    boost = {
        "id": "c1",
        "origin": "claim",
        "claim_status": "ratified",
        "confidence": 0.8,
        "linked_goal_id": "g1",
    }
    assert may_influence_agency_ranking(boost)
    ranked = rank_goals_for_agency(goals, meaning_boosts=[boost])
    assert ranked[0]["id"] == "g1"

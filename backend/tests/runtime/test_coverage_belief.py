"""Coverage tests for Belief projectors (BeliefFormed / Strengthened / Revoked)."""
import pytest


def test_belief_formed_inserts_memory(isolated_kernel):
    """BeliefFormed inserts a memory row with belief metadata."""
    k, _db = isolated_kernel
    k.emit_event("BeliefFormed", "memory", "belief_1", payload={
        "category": "pattern", "content": "User codes daily",
        "source": "reflection", "confidence": 0.8,
        "derived_from_event": "evt_123",
    }, actor="agent:planner")

    with _db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", ("belief_1",)
        ).fetchone()
        assert row is not None
        assert row["category"] == "pattern"
        assert row["content"] == "User codes daily"
        assert row["claim_status"] in ("inferred", "proposed")


def test_belief_strengthened_updates_confidence(isolated_kernel):
    """BeliefStrengthened updates confidence on existing memory."""
    k, _db = isolated_kernel
    k.emit_event("MemoryDerived", "memory", "belief_2", payload={
        "category": "fact", "content": "Prefers morning", "confidence": 0.5,
    }, actor="agent:planner")
    k.emit_event("BeliefStrengthened", "memory", "belief_2", payload={
        "confidence": 0.9,
    }, actor="agent:planner")

    with _db.get_db() as conn:
        row = conn.execute(
            "SELECT confidence FROM memories WHERE id = ?", ("belief_2",)
        ).fetchone()
        assert row is not None
        assert row["confidence"] == 0.9


def test_belief_revoked_sets_confidence_zero(isolated_kernel):
    """BeliefRevoked sets confidence=0 and status=revoked."""
    k, _db = isolated_kernel
    k.emit_event("MemoryDerived", "memory", "belief_3", payload={
        "category": "fact", "content": "Old fact", "confidence": 0.7,
    }, actor="agent:planner")
    k.emit_event("BeliefRevoked", "memory", "belief_3", payload={},
                 actor="agent:planner")

    with _db.get_db() as conn:
        row = conn.execute(
            "SELECT confidence, status, claim_status FROM memories WHERE id = ?",
            ("belief_3",),
        ).fetchone()
        assert row is not None
        assert row["confidence"] == 0.0
        assert row["status"] == "revoked"
        assert row["claim_status"] == "rejected"


def test_belief_strengthened_no_existing_row(isolated_kernel):
    """BeliefStrengthened on non-existing row should not crash."""
    k, _db = isolated_kernel
    k.emit_event("BeliefStrengthened", "memory", "nonexistent",
                 payload={"confidence": 0.5}, actor="agent:planner")
    # Should complete without error

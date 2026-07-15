"""Egress gate tests."""

from app.core.runtime.egress.egress_gate import audit_llm_egress, classify_llm_payload
from app.core.runtime.kernel import Kernel
from app.store.database import Database


def test_classify_identity_surface():
    cats = classify_llm_payload(
        [{"role": "user", "content": "claim_status identity_narrative_opt_in"}]
    )
    assert "identity_surface" in cats["categories"]


def test_egress_emits_audit_event(tmp_path):
    import app.core.runtime.kernel_instance as ki

    saved = ki.kernel
    try:
        db = Database(db_path=str(tmp_path / "egress.db"))
        k = Kernel(db=db)
        ki.kernel = k
        _, audit = audit_llm_egress(
            [{"role": "user", "content": "hello"}], purpose="test"
        )
        assert audit["purpose"] == "test"
        events = k.read_events(type="EgressAudited")
        assert len(events) == 1
    finally:
        ki.kernel = saved


def test_audit_llm_egress_returns_messages_and_audit(tmp_path):
    """Regression: callers in inbox.py / api/goals.py must consume the tuple.

    A prior commit invoked the egress helper as a void function and redeclared
    the messages list separately, which meant the audited payload could drift
    from the payload actually sent to the LLM. This test pins the contract:
    the first tuple element equals the input messages (audit-only, no
    mutation), and the second carries classification metadata.
    """
    import app.core.runtime.kernel_instance as ki

    saved = ki.kernel
    try:
        db = Database(db_path=str(tmp_path / "egress.db"))
        k = Kernel(db=db)
        ki.kernel = k

        original = [
            {"role": "system", "content": "classifier"},
            {"role": "user", "content": "email body"},
        ]
        returned_messages, audit = audit_llm_egress(
            original, purpose="inbox_classify", actor="inbox",
        )

        # Audit-only contract: messages pass through unchanged.
        assert returned_messages is original
        assert returned_messages == original
        # Audit metadata carries purpose, actor-agnostic fields.
        assert audit["purpose"] == "inbox_classify"
        assert "classification" in audit
        assert audit["classification"]["message_count"] == 2

        events = k.read_events(type="EgressAudited")
        assert len(events) == 1
        ev = events[0]
        assert ev.payload["purpose"] == "inbox_classify"
        # actor is an emit_event parameter, recorded on the event row itself.
        assert ev.actor == "inbox"
    finally:
        ki.kernel = saved


def test_audit_llm_egress_goal_breakdown_audit(tmp_path):
    """Covers the api/goals.py goal_breakdown path (Low #19 closure)."""
    import app.core.runtime.kernel_instance as ki

    saved = ki.kernel
    try:
        db = Database(db_path=str(tmp_path / "egress.db"))
        k = Kernel(db=db)
        ki.kernel = k

        messages = [
            {"role": "system", "content": "You break goals into steps."},
            {"role": "user", "content": "Goal: ship release"},
        ]
        returned_messages, audit = audit_llm_egress(
            messages, purpose="goal_breakdown", actor="api",
        )

        assert returned_messages is messages
        assert audit["purpose"] == "goal_breakdown"
        events = k.read_events(type="EgressAudited")
        assert len(events) == 1
        assert events[0].actor == "api"
    finally:
        ki.kernel = saved


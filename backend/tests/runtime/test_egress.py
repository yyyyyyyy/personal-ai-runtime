"""Egress gate tests."""

from app.core.runtime.egress.egress_gate import classify_llm_payload, prepare_llm_egress
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
        _, audit = prepare_llm_egress(
            [{"role": "user", "content": "hello"}], purpose="test"
        )
        assert audit["purpose"] == "test"
        events = k.read_events(type="EgressApproved")
        assert len(events) == 1
    finally:
        ki.kernel = saved

"""Meaning DAG audit — MEANING_ONTOLOGY §3.2."""

from app.core.runtime.kernel import Kernel
from app.core.runtime.kernel.event import Event
from app.core.runtime.meaning_dag import audit_meaning_dag, classify_meaning_layer
from app.store.database import Database


def test_classify_claim_layer():
    e = Event(
        type="MemoryDerived",
        aggregate_type="memory",
        aggregate_id="m1",
        payload={"origin": "claim", "belief_type": "claim"},
    )
    assert classify_meaning_layer(e) == "claim"


def test_trajectory_linked_from_claim_is_fail():
    claim = Event(
        type="MemoryDerived",
        aggregate_type="memory",
        aggregate_id="c1",
        payload={"origin": "claim"},
        id="evt_claim",
        seq=1,
    )
    link = Event(
        type="TrajectoryLinked",
        aggregate_type="trajectory",
        aggregate_id="t1",
        payload={"link_id": "l1", "event_seq": 1},
        caused_by="evt_claim",
        seq=2,
    )
    failures, _ = audit_meaning_dag([claim, link])
    assert any("TrajectoryLinked" in f for f in failures)


def test_valid_cite_down_passes():
    mem = Event(
        type="MemoryDerived",
        aggregate_type="memory",
        aggregate_id="m1",
        payload={"content": "observation"},
        id="evt_mem",
        seq=10,
    )
    link = Event(
        type="TrajectoryLinked",
        aggregate_type="trajectory",
        aggregate_id="t1",
        payload={"link_id": "l1", "event_seq": 10},
        seq=11,
    )
    failures, _ = audit_meaning_dag([mem, link])
    assert not failures


def test_kernel_fixture_clean(tmp_path):
    db = Database(db_path=str(tmp_path / "meaning_dag.db"))
    k = Kernel(db=db)
    src = k.emit_event(
        "MemoryDerived", "memory", "m-dag",
        payload={"content": "test"}, actor="user",
    )
    assert src.seq is not None
    k.emit_event(
        "TrajectoryLinked", "trajectory", "t-dag",
        payload={"link_id": "lk1", "event_seq": src.seq, "claim_status": "proposed"},
        actor="system",
    )
    from app.core.runtime.meaning_dag import audit_kernel_event_log

    failures, _ = audit_kernel_event_log(k)
    assert not failures

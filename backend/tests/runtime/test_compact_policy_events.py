"""Unit tests for policy event compaction helper."""

from __future__ import annotations

from scripts.compact_policy_events import _replay_policy, _synthetic_rows


def _tpl(**over):
    base = {"ts": "2026-07-23T09:39:31Z", "caused_by": None, "correlation_id": None, "actor": "kernel"}
    base.update(over)
    return base


def test_replay_created_only():
    state = _replay_policy([
        {
            "type": "PolicyCreated",
            "payload": {"capability": "x", "risk_level": "high"},
        },
    ])
    assert state == {"capability": "x", "risk_level": "high", "status": "active"}


def test_replay_revoke_reactivate():
    state = _replay_policy([
        {"type": "PolicyCreated", "payload": {"capability": "x", "risk_level": "low"}},
        {"type": "PolicyUpdated", "payload": {"capability": "x", "status": "revoked"}},
        {
            "type": "PolicyUpdated",
            "payload": {"capability": "x", "status": "active", "risk_level": "high"},
        },
    ])
    assert state == {"capability": "x", "risk_level": "high", "status": "active"}


def test_synthetic_active_preserves_template_provenance():
    rows = _synthetic_rows(
        "policy_x",
        {"capability": "x", "risk_level": "low", "status": "active"},
        template=_tpl(ts="2026-01-01T00:00:00Z", caused_by="evt_orig_42", correlation_id="c1"),
        start_seq=10,
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["type"] == "PolicyCreated"
    assert r["seq"] == 10
    assert r["ts"] == "2026-01-01T00:00:00Z"
    assert r["caused_by"] == "evt_orig_42"
    assert r["correlation_id"] == "c1"
    assert r["actor"] == "kernel"


def test_synthetic_revoked_links_chain_and_uses_template_ts():
    rows = _synthetic_rows(
        "policy_x",
        {"capability": "x", "risk_level": "low", "status": "revoked"},
        template=_tpl(ts="2026-02-02T00:00:00Z"),
        start_seq=10,
    )
    assert len(rows) == 2
    assert rows[1]["type"] == "PolicyUpdated"
    assert rows[1]["payload"]["status"] == "revoked"
    # revoke links to the synthetic create, not the original template
    assert rows[1]["caused_by"] == rows[0]["id"]
    # both share the template ts (collapsed burst)
    assert rows[0]["ts"] == "2026-02-02T00:00:00Z"
    assert rows[1]["ts"] == "2026-02-02T00:00:00Z"


def test_synthetic_falls_back_when_template_missing_actor():
    rows = _synthetic_rows(
        "policy_x",
        {"capability": "x", "risk_level": "low", "status": "active"},
        template={"ts": "t0", "caused_by": None, "correlation_id": None, "actor": None},
        start_seq=1,
    )
    assert rows[0]["actor"] == "compact_policy_events"


def test_compact_preserves_global_seq_and_ts_order():
    """End-to-end on plan_compaction: seq contiguous + ts monotonic + provenance."""
    from scripts.compact_policy_events import plan_compaction

    raw = [
        {"seq": 1, "id": "e1", "type": "TimerCreated", "aggregate_type": "timer", "aggregate_id": "t1", "actor": "system", "payload": "{}", "caused_by": None, "correlation_id": None, "ts": "2026-01-01T00:00:00Z"},
        {"seq": 2, "id": "e2", "type": "PolicyCreated", "aggregate_type": "policy", "aggregate_id": "policy_x", "actor": "kernel", "payload": '{"capability":"x","risk_level":"low"}', "caused_by": "evt_orig_42", "correlation_id": "c1", "ts": "2026-01-01T00:00:01Z"},
        {"seq": 3, "id": "e3", "type": "PolicyUpdated", "aggregate_type": "policy", "aggregate_id": "policy_x", "actor": "kernel", "payload": '{"capability":"x","status":"revoked"}', "caused_by": None, "correlation_id": None, "ts": "2026-01-01T00:00:02Z"},
        {"seq": 4, "id": "e4", "type": "PolicyCreated", "aggregate_type": "policy", "aggregate_id": "policy_x", "actor": "kernel", "payload": '{"capability":"x","risk_level":"high"}', "caused_by": None, "correlation_id": None, "ts": "2026-01-01T00:00:03Z"},
        {"seq": 5, "id": "e5", "type": "MemoryUpdated", "aggregate_type": "memory", "aggregate_id": "m1", "actor": "system", "payload": "{}", "caused_by": None, "correlation_id": None, "ts": "2026-01-01T00:00:04Z"},
        {"seq": 6, "id": "e6", "type": "PolicyCreated", "aggregate_type": "policy", "aggregate_id": "policy_y", "actor": "kernel", "payload": '{"capability":"y","risk_level":"low"}', "caused_by": None, "correlation_id": None, "ts": "2026-01-01T00:00:05Z"},
    ]

    output, stats = plan_compaction(raw)

    # stats sanity
    assert stats["total"] == 6
    assert stats["policy_before"] == 4
    assert stats["policy_kept"] == 2
    assert stats["policy_removed"] == 2
    assert stats["after"] == 4

    # seq contiguous 1..N
    seqs = [int(r["seq"]) for r in output]
    assert seqs == list(range(1, len(output) + 1)), f"non-contiguous seq: {seqs}"

    # ts non-decreasing globally
    tss = [r["ts"] for r in output]
    assert tss == sorted(tss), f"ts not monotonic: {tss}"

    # policy_x collapsed to one PolicyCreated (active, high) at original seq slot
    px = [r for r in output if r["aggregate_id"] == "policy_x"]
    assert len(px) == 1
    assert px[0]["type"] == "PolicyCreated"
    assert px[0]["payload"]["risk_level"] == "high"
    # ts preserved from the ORIGINAL first event of policy_x
    assert px[0]["ts"] == "2026-01-01T00:00:01Z"
    # caused_by preserved from the ORIGINAL first event (data fidelity)
    assert px[0]["caused_by"] == "evt_orig_42"
    assert px[0]["correlation_id"] == "c1"

    # MemoryUpdated (seq 5 originally) stays after policy_x's slot
    mem = next(r for r in output if r["type"] == "MemoryUpdated")
    assert int(mem["seq"]) > int(px[0]["seq"])

    # TimerCreated (seq 1 originally) stays first
    assert output[0]["type"] == "TimerCreated"

    # policy_y single PolicyCreated preserved
    py = [r for r in output if r["aggregate_id"] == "policy_y"]
    assert len(py) == 1
    assert py[0]["ts"] == "2026-01-01T00:00:05Z"

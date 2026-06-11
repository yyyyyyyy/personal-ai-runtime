#!/usr/bin/env python
"""Meaning DAG verification — MEANING_ONTOLOGY §3.2 upward generation guard."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.core.runtime.meaning_dag import audit_kernel_event_log, audit_meaning_dag
from app.core.runtime.trajectory.engine import link_event
from app.store.database import Database


def _run_negative_fixture() -> list[str]:
    """Synthetic violations must be detected."""
    db_path = _BACKEND_ROOT / "data" / "verify_meaning_dag_negative.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    claim = k.emit_event(
        "MemoryDerived",
        "memory",
        "dag-claim",
        payload={"content": "系统推断", "origin": "claim", "belief_type": "claim"},
        actor="system",
    )
    assert claim.seq is not None

    bad_link = k.emit_event(
        "TrajectoryLinked",
        "trajectory",
        "career-entrepreneurship-2026",
        payload={
            "link_id": "bad_dag_link",
            "event_seq": claim.seq,
            "claim_status": "proposed",
            "source_belief_id": "blf-test",
        },
        actor="system",
        caused_by=claim.id,
    )
    _ = bad_link

    failures, _warnings = audit_kernel_event_log(k)
    if not failures:
        return ["negative fixture: expected DAG failures but got none"]
    return []


def main() -> int:
    violations: list[str] = []

    db_path = _BACKEND_ROOT / "data" / "verify_meaning_dag.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(db_path))
    k = Kernel(db=db)

    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = db

    # Valid fixture: TrajectoryLinked cites representation event_seq (cite-down OK)
    src = k.emit_event(
        "MemoryDerived",
        "memory",
        "dag-mem",
        payload={"content": "想创业"},
        actor="user",
    )
    assert src.seq is not None
    link_event(k, "career-entrepreneurship-2026", src.seq, actor="system")

    failures, warnings = audit_kernel_event_log(k)
    violations.extend(failures)
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    violations.extend(_run_negative_fixture())

    if violations:
        print("MEANING DAG VERIFICATION FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("MEANING DAG VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

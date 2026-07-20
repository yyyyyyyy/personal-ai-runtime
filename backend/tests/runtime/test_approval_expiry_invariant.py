"""Invariant: approval expiry must not bypass projectors.

GOVERNED ``approvals`` status changes only via ApprovalDenied projection.
``expire_stale_approvals`` emits events; it must not UPDATE approvals itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

def test_expire_stale_approvals_emit_only_projects_expired(isolated_kernel):
    k, _db = isolated_kernel
    k.emit_event(
        "WorkItemCreated", "work_item", "ge",
        payload={"work_type": "goal", "title": "Expiry"},
    )
    k.emit_event(
        "ApprovalRequested",
        "approval",
        "app-inv",
        payload={
            "work_type": "goal",
            "task_id": "ge",
            "action": "shell_exec",
            "params": {},
            "proposed_by": "runtime:test",
        },
    )
    # Test fixture only: force expires_at into the past (not a production path).
    with k._db.get_db() as conn:
        conn.execute(
            "UPDATE approvals SET expires_at = '2020-01-01T00:00:00' "
            "WHERE id = 'app-inv'"
        )

    count = k.expire_stale_approvals()
    assert count == 1

    row = k.query_state("approvals", id="app-inv")[0]
    assert row["status"] == "expired"

    events = [
        e for e in k.read_events()
        if e.type == "ApprovalDenied" and e.aggregate_id == "app-inv"
    ]
    assert len(events) == 1
    assert events[0].payload.get("reason") == "auto_expired"

def test_expire_idempotent_when_already_expired(isolated_kernel):
    k, _db = isolated_kernel
    k.emit_event(
        "ApprovalRequested",
        "approval",
        "app-idem",
        payload={
            "task_id": "t1",
            "action": "shell_exec",
            "params": {},
            "proposed_by": "runtime:test",
        },
    )
    with k._db.get_db() as conn:
        conn.execute(
            "UPDATE approvals SET expires_at = '2020-01-01T00:00:00' "
            "WHERE id = 'app-idem'"
        )

    assert k.expire_stale_approvals() == 1
    assert k.expire_stale_approvals() == 0  # no longer pending
    assert k.query_state("approvals", id="app-idem")[0]["status"] == "expired"

def test_governance_ops_has_no_approvals_dml():
    """Static invariant: governance_ops must not UPDATE/INSERT/DELETE approvals."""
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "core"
        / "runtime"
        / "kernel"
        / "governance_ops.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value.lower()
            if "approvals" not in sql:
                continue
            if any(
                kw in sql
                for kw in ("update approvals", "insert into approvals", "delete from approvals")
            ):
                pytest.fail(
                    f"governance_ops.py contains GOVERNED DML on approvals: {node.value!r}"
                )

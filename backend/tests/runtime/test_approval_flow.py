"""Kernel-level approval flow (pending → pre_approved / grant / deny).

Not an HTTP integration test — lives under tests/runtime.
"""

import pytest


@pytest.mark.asyncio
async def test_high_risk_capability_pending_then_approve(isolated_kernel):
    k, _db = isolated_kernel
    cap = await k.invoke_capability(
        "write_file", {"path": "/tmp/x", "content": "hi"}, actor="user"
    )
    assert cap["status"] == "pending"
    approval_id = cap["approval_id"]

    cap2 = await k.invoke_capability(
        "write_file",
        {"path": "/tmp/x", "content": "hi"},
        actor="user",
        correlation_id="retry",
        pre_approved=True,
        approval_id=approval_id,
    )
    assert cap2["status"] == "success"


@pytest.mark.asyncio
async def test_apply_patch_pending_then_approve(isolated_kernel):
    k, _db = isolated_kernel
    cap = await k.invoke_capability(
        "apply_patch",
        {"path": "/tmp/app.py", "old_string": "a", "new_string": "b"},
        actor="user",
    )
    assert cap["status"] == "pending"
    approval_id = cap["approval_id"]

    cap2 = await k.invoke_capability(
        "apply_patch",
        {"path": "/tmp/app.py", "old_string": "a", "new_string": "b"},
        actor="user",
        correlation_id="patch-retry",
        pre_approved=True,
        approval_id=approval_id,
    )
    assert cap2["status"] == "success"


def test_request_approval_via_kernel(isolated_kernel):
    k, _db = isolated_kernel
    result = k.request_approval(
        action="write_file",
        risk="high",
        ctx={"args": {"path": "/tmp/test"}, "proposed_by": "agent:planner"},
        actor="agent:planner",
    )
    assert result is not None
    assert result["status"] == "pending"


def test_approve_lifecycle_via_kernel(isolated_kernel):
    k, _db = isolated_kernel
    result = k.request_approval(
        action="read_file",
        risk="high",
        ctx={"args": {"path": "/tmp/read"}, "proposed_by": "agent:planner"},
        actor="agent:planner",
    )
    k.grant_approval(
        result["approval_id"], action="read_file", actor="user", reason="test",
    )
    approval = k.query_state("approvals", id=result["approval_id"])
    assert len(approval) == 1
    assert approval[0]["status"] == "approved"


def test_reject_approval_via_kernel(isolated_kernel):
    k, _db = isolated_kernel
    result = k.request_approval(
        action="shell_exec",
        risk="high",
        ctx={"args": {"command": "ls"}, "proposed_by": "agent:planner"},
        actor="agent:planner",
    )
    k.deny_approval(
        result["approval_id"], action="shell_exec", actor="user",
        reason="test reject",
    )
    approval = k.query_state("approvals", id=result["approval_id"])
    assert len(approval) == 1
    assert approval[0]["status"] in ("rejected", "denied")


def test_get_approval_missing(isolated_kernel):
    from app.core.runtime.capability_governance import CapabilityGovernance

    k, _db = isolated_kernel
    assert CapabilityGovernance.get_approval(k, "nonexistent") is None


def test_request_approval_with_task_id_via_kernel(isolated_kernel):
    k, _db = isolated_kernel
    result = k.request_approval(
        action="apply_patch",
        risk="high",
        ctx={
            "task_id": "task_123",
            "args": {"old": "a", "new": "b"},
            "proposed_by": "agent:planner",
        },
        actor="agent:planner",
    )
    assert result is not None

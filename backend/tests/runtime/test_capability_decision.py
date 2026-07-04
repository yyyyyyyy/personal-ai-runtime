"""ADR-0007 Step 9 — CapabilityDecision and CapabilityGateway tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "cap_decision.db")))


def test_capability_decision_allow(kernel):
    """System principal with wildcard capabilities is allowed for low-risk tools."""
    from app.core.runtime.capability_governance import capability_governance as capability_gateway
    from app.core.runtime.execution import Principal

    decision = capability_gateway.decide(
        Principal.system(),
        "get_current_time",
        {},
        kernel,
    )
    assert decision.decision == "allow"


def test_capability_decision_deny_principal_not_authorized(kernel):
    """Agent principal without the capability in its whitelist is denied."""
    from app.core.runtime.capability_governance import capability_governance as capability_gateway
    from app.core.runtime.execution import Principal

    principal = Principal.agent("aginst_test", ["web_search"])
    decision = capability_gateway.decide(
        principal,
        "shell_exec",
        {},
        kernel,
    )
    assert decision.decision == "deny"
    assert decision.reason == "principal_not_authorized"


def test_capability_decision_fail_closed_for_empty_agent(kernel):
    """Agent principal with empty capabilities and no wildcard is denied."""
    from app.core.runtime.capability_governance import capability_governance as capability_gateway
    from app.core.runtime.execution import Principal

    principal = Principal.agent("aginst_test", [])
    decision = capability_gateway.decide(
        principal,
        "web_search",
        {},
        kernel,
    )
    assert decision.decision == "deny"
    assert "principal_not_authorized" in decision.reason or "not_authorized" in decision.reason


@pytest.mark.asyncio
async def test_invoke_capability_uses_principal(kernel):
    """invoke_capability resolves Principal from actor and delegates to gateway."""
    # Use a system principal to invoke a low-risk capability
    result = await kernel.invoke_capability(
        name="get_current_time",
        actor="system",
    )
    # The result should either succeed or error (tool may not be registered
    # in test env) — but should NOT be denied for auth reasons
    assert result["status"] in ("success", "error")
    if result["status"] == "error":
        assert "Denied" not in result.get("error", "")


@pytest.mark.asyncio
async def test_invoke_capability_denies_unauthorized_agent(kernel):
    """Agent principal without capabilities is denied by invoke_capability."""
    from app.core.runtime.kernel.constants import AGGREGATE_EXECUTION, EVENT_EXECUTION_REQUESTED
    from app.core.runtime.execution import Principal

    eid = "wi_agent_deny"
    kernel.emit_event(
        EVENT_EXECUTION_REQUESTED,
        AGGREGATE_EXECUTION,
        eid,
        payload={
            "execution_id": eid,
            "handler_name": "on_test",
            "trigger_event_id": "evt_a",
            "trigger_event_seq": 1,
            "trigger_event_type": "TaskCreated",
            "instance_id": "inst_a",
            "policy": {},
            "event_seq": 1,
        },
        actor="scheduler",
    )

    principal = Principal.agent("aginst_noperm", [])
    result = await kernel.invoke_capability(
        name="web_search",
        actor="agent:aginst_noperm",
        principal=principal,
        execution_id=eid,
    )
    assert result["status"] == "error"
    assert "principal_not_authorized" in result["error"]


def test_resolve_agent_capabilities_deleted(kernel):
    """_resolve_agent_capabilities should no longer exist on Kernel (Step 9)."""
    assert not hasattr(kernel, "_resolve_agent_capabilities")

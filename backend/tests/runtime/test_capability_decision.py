"""Execution 契约 §9 — CapabilityDecision and CapabilityGovernance tests.

The runtime only emits system/user principals.
"""

from __future__ import annotations

import pytest

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k

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

@pytest.mark.asyncio
async def test_invoke_capability_uses_principal(kernel):
    """invoke_capability resolves Principal from actor and delegates to gateway."""
    result = await kernel.invoke_capability(
        name="get_current_time",
        actor="system",
    )
    assert result["status"] in ("success", "error")
    if result["status"] == "error":
        assert "Denied" not in result.get("error", "")

def test_resolve_agent_capabilities_deleted(kernel):
    """_resolve_agent_capabilities should no longer exist on Kernel (Step 9)."""
    assert not hasattr(kernel, "_resolve_agent_capabilities")

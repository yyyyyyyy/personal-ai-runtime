"""ADR-0007 Step 9 — CapabilityDecision and CapabilityGovernance tests.

v0.9.0: agent principal tests removed — Principal.agent was deleted along
with Gate 2 (grant_events). The runtime now only emits system/user principals.
"""

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

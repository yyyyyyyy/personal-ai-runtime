"""A3 — forbidden policy path: Gate 1 deny + CapabilityDenied + tool not executed."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database

    return Kernel(db=Database(db_path=str(tmp_path / "forbidden.db")))


def test_forbidden_policy_gateway_gate1(kernel):
    """Gate 1: policy_events risk_level=forbidden → deny before principal checks."""
    from app.core.runtime.capability_governance import capability_governance as capability_gateway
    from app.core.runtime.execution import Principal

    kernel.emit_event(
        "PolicyCreated",
        "policy",
        "policy_forbidden_get_current_time",
        payload={"capability": "get_current_time", "risk_level": "forbidden"},
        actor="test",
    )

    decision = capability_gateway.decide(
        Principal.user(),
        "get_current_time",
        {},
        kernel,
    )
    assert decision.decision == "deny"
    assert decision.reason == "forbidden_by_policy"


@pytest.mark.asyncio
async def test_forbidden_policy_denies_capability(kernel):
    """PolicyCreated(forbidden) → invoke_capability denies, emits event, never runs tool."""
    kernel.emit_event(
        "PolicyCreated",
        "policy",
        "policy_forbidden_get_current_time",
        payload={"capability": "get_current_time", "risk_level": "forbidden"},
        actor="test",
    )

    with patch(
        "app.core.harness.mcp_hub.mcp_hub.invoke_tool",
        new_callable=AsyncMock,
    ) as mock_invoke:
        result = await kernel.invoke_capability(
            "get_current_time",
            {},
            actor="user",
            correlation_id="corr_forbidden",
        )

    assert result["status"] == "error"
    assert result["error"] == "forbidden_by_policy"
    mock_invoke.assert_not_called()

    events = kernel.read_events(correlation_id="corr_forbidden")
    denied = [e for e in events if e.type == "CapabilityDenied"]
    assert len(denied) == 1
    assert denied[0].payload.get("name") == "get_current_time"
    assert denied[0].payload.get("reason") == "forbidden_by_policy"
    assert not any(e.type == "CapabilityInvoked" for e in events)

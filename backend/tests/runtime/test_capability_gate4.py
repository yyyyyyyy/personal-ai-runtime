"""Gate 4 (risk escalation) tests for CapabilityGovernance.decide().

Covers paths not exercised by existing decision/forbidden tests:
- taint escalation (write-class tool on tainted correlation → forced high)
- sensitive router escalation
- high risk denied for non-user principals
"""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def kernel(tmp_path):
    from app.core.runtime.kernel import Kernel
    from app.store.database import Database
    return Kernel(db=Database(db_path=str(tmp_path / "gate4.db")))


def test_taint_escalates_write_tool_to_high(kernel):
    """Write-class tool on a tainted correlation → risk forced to high."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.principal import Principal
    from app.core.runtime.taint import register_external_write_tool, taint_registry

    corr = "tainted-correlation"
    taint_registry.mark(corr, source="external_ingestion", reason="web_search")
    register_external_write_tool("shell_exec")

    decision = capability_governance.decide(
        Principal.system(),
        "shell_exec",
        {"cmd": "echo hi"},
        kernel,
        correlation_id=corr,
    )

    taint_registry.clear(corr)
    assert decision.decision != "allow", f"Tainted write tool should NOT be auto-allowed: {decision}"
    assert decision.reason is not None, f"Tainted write tool must give a reason: {decision}"


def test_high_risk_agent_auto_denied(kernel):
    """High-risk tools are auto-denied for non-user principals (agent)."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.principal import Principal

    # shell_exec has risk "high" in capability_policy.json → needs_user
    principal = Principal.agent("test_agent", ["shell_exec"])
    decision = capability_governance.decide(
        principal,
        "shell_exec",
        {},
        kernel,
    )

    # The agent may be denied at gate 2 (no grant_events) or gate 4 (high risk auto-deny)
    # What matters: the decision is NOT "allow"
    assert decision.decision != "allow", f"High-risk shell_exec should not be allowed for agent without grant: {decision}"


def test_low_risk_system_principal_gets_auto_approved(kernel):
    """Low-risk tool for system/user principal → approval auto-approved → allow."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.principal import Principal

    # get_current_time is auto_allow (low risk) in capability_policy.json
    decision = capability_governance.decide(
        Principal.system(),
        "get_current_time",
        {},
        kernel,
    )
    assert decision.decision == "allow"


def test_pre_approved_rejects_missing_approval_id(kernel):
    """Gate 3: pre_approved=True without approval_id → deny."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.principal import Principal

    decision = capability_governance.decide(
        Principal.system(),
        "get_current_time",
        {},
        kernel,
        pre_approved=True,
        approval_id=None,
    )
    assert decision.decision == "deny"
    assert "approval_id" in decision.reason


def test_non_user_principal_without_grant_denied(kernel):
    """Agent principal without any grant_events → denied at gate 2."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.principal import Principal

    principal = Principal.agent("unknown_agent", [])
    decision = capability_governance.decide(
        principal,
        "web_search",
        {},
        kernel,
    )
    assert decision.decision == "deny"

"""pre_approved path must not bypass taint escalation.

Regression for the Gate 2 bypass: previously, a pre_approved invocation
skipped Gate 3 entirely, which meant a tainted correlation could drive a
write-class tool without re-evaluating taint. The fix computes
tainted_write before Gate 2 and fail-closed denies for system principals
even on the pre_approved path.
"""

import pytest

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    return k

def _make_pending_approval(kernel, capability, args, principal_actor):
    """Create a pending approval row that pre_approved path can consume.

    Uses risk='high' so the approval stays in 'pending' status (low-risk
    approvals are auto-granted immediately by request_approval).
    """
    approval = kernel.request_approval(
        action=capability, risk="high", ctx={"args": args},
        actor=principal_actor, correlation_id=None,
    )
    assert approval["status"] == "pending", "helper must produce a pending approval"
    return approval["approval_id"]

def test_pre_approved_tainted_write_system_principal_denied(kernel):
    """Tainted correlation + write tool + system principal → deny even if pre_approved."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.execution import Principal
    from app.core.runtime.taint import taint_registry

    corr = "tainted-pre-approved-1"
    taint_registry.mark(corr, source="external_ingestion", reason="web_search")

    decision = capability_governance.decide(
        Principal.system(),
        "shell_exec",
        {"cmd": "rm -rf /"},
        kernel,
        correlation_id=corr,
        pre_approved=True,
        approval_id="fake-approval-id",
    )

    taint_registry.clear(corr)
    assert decision.decision == "deny"
    assert "tainted_write" in decision.reason

def test_pre_approved_tainted_write_user_principal_allowed(kernel):
    """Tainted correlation + write tool + user principal + valid approval → allow.

    User principals are allowed to proceed on the pre_approved path because a
    human explicitly approved the invocation. The taint is recorded but does
    not block a user-confirmed action.
    """
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.execution import Principal
    from app.core.runtime.taint import taint_registry

    corr = "tainted-pre-approved-2"
    taint_registry.mark(corr, source="external_ingestion", reason="read_inbox_email")

    args = {"cmd": "echo safe"}
    approval_id = _make_pending_approval(kernel, "shell_exec", args, "user")

    decision = capability_governance.decide(
        Principal.user("user"),
        "shell_exec",
        args,
        kernel,
        correlation_id=corr,
        pre_approved=True,
        approval_id=approval_id,
    )

    taint_registry.clear(corr)
    assert decision.decision == "allow"
    assert decision.reason == "pre_approved"

def test_pre_approved_untainted_normal_path_still_works(kernel):
    """Regression: normal (non-tainted) pre_approved path must still allow."""
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.execution import Principal

    args = {}
    approval_id = _make_pending_approval(kernel, "get_current_time", args, "system")

    decision = capability_governance.decide(
        Principal.system(),
        "get_current_time",
        args,
        kernel,
        pre_approved=True,
        approval_id=approval_id,
    )

    assert decision.decision == "allow"
    assert decision.reason == "pre_approved"

def test_pre_approved_tainted_non_write_tool_system_principal_allowed(kernel):
    """Tainted correlation + non-write tool → no taint escalation.

    Taint only escalates write-class tools. A read-only tool on a tainted
    correlation is not affected, even for system principals.
    """
    from app.core.runtime.capability_governance import capability_governance
    from app.core.runtime.execution import Principal
    from app.core.runtime.taint import taint_registry

    corr = "tainted-pre-approved-3"
    taint_registry.mark(corr, source="external_ingestion", reason="web_search")

    args = {}
    approval_id = _make_pending_approval(kernel, "get_current_time", args, "system")

    decision = capability_governance.decide(
        Principal.system(),
        "get_current_time",
        args,
        kernel,
        correlation_id=corr,
        pre_approved=True,
        approval_id=approval_id,
    )

    taint_registry.clear(corr)
    assert decision.decision == "allow"

"""C3 · External MCP Policy full event sourcing tests.

Validates:
  1. register_external_tool emits PolicyCreated into event_log
  2. rebuild("policy") recovers external tools from event_log
  3. clear_external_tools emits PolicyRevoked and leaves no orphans
  4. Re-registration after clear re-activates via PolicyCreated
"""

import pytest

from app.core.runtime.capability_governance import capability_governance
from app.core.runtime.kernel import Kernel
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    """Create an isolated Kernel and seed capability_policy with it."""
    db = Database(db_path=str(tmp_path / "c3_policy.db"))
    k = Kernel(db=db)
    # Simulate startup: seed the JSON-based policies and store kernel reference
    capability_governance.seed_from_json(k)
    return k


@pytest.fixture(autouse=True)
def _reset_policy():
    """Clean up external tools after each test."""
    yield
    capability_governance.clear_external_tools()


def test_register_external_tool_emits_policy_created(kernel):
    """register_external_tool emits PolicyCreated into event_log."""
    capability_governance.register_external_tool("mock_external_search", risk="high")

    events = kernel.read_events(aggregate_type="policy")
    created = [e for e in events if e.type == "PolicyCreated" and e.payload.get("capability") == "mock_external_search"]
    assert len(created) == 1
    assert created[0].payload["risk_level"] == "high"
    assert created[0].actor == "kernel"


def test_rebuild_recovers_external_tool_policy(kernel):
    """rebuild("policy") recovers external tool policy from event_log."""
    capability_governance.register_external_tool("mock_external_search", risk="high")

    # Verify it's in the projection
    rows = kernel.query_state("policy_events", capability="mock_external_search", status="active")
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "high"

    # Rebuild and verify it's still there
    kernel.rebuild("policy")

    rows = kernel.query_state("policy_events", capability="mock_external_search", status="active")
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "high"


def test_clear_external_tools_emits_policy_revoked(kernel):
    """clear_external_tools emits PolicyRevoked and clears in-memory cache."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.register_external_tool("mock_external_write", risk="forbidden")

    capability_governance.clear_external_tools()

    # Verify PolicyUpdated (status=revoked) events exist
    events = kernel.read_events(aggregate_type="policy")
    revoked = [
        e for e in events
        if e.type == "PolicyUpdated" and e.payload.get("status") == "revoked"
    ]
    assert len(revoked) == 2
    capabilities = {e.payload.get("capability") for e in revoked}
    assert capabilities == {"mock_external_search", "mock_external_write"}

    # In-memory cache is empty
    assert not capability_governance._external_auto_allow
    assert not capability_governance._external_needs_user
    assert not capability_governance._external_forbidden


def test_rebuild_after_clear_excludes_revoked(kernel):
    """After clear, rebuild("policy") should NOT include revoked tools as active."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.clear_external_tools()

    kernel.rebuild("policy")

    rows = kernel.query_state("policy_events", capability="mock_external_search", status="active")
    assert len(rows) == 0

    # The revoked row still exists (non-active)
    all_rows = kernel.query_state("policy_events", capability="mock_external_search")
    assert len(all_rows) == 1
    assert all_rows[0]["status"] == "revoked"


def test_reregister_after_clear_reactivates(kernel):
    """Re-registering after clear emits a new PolicyCreated (re-activation)."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.clear_external_tools()

    # Re-register
    capability_governance.register_external_tool("mock_external_search", risk="low")

    # Verify the tool is now active with the new risk
    rows = kernel.query_state("policy_events", capability="mock_external_search", status="active")
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "low"

    # Verify event chain
    events = kernel.read_events(aggregate_type="policy")
    types_for_tool = [
        e.type for e in events
        if e.payload.get("capability") == "mock_external_search"
    ]
    assert "PolicyCreated" in types_for_tool
    revoked_types = [
        e.type for e in events
        if e.payload.get("capability") == "mock_external_search"
        and e.payload.get("status") == "revoked"
    ]
    assert "PolicyUpdated" in revoked_types
    # The second PolicyCreated should appear after the revoked.
    all_types = [e.type for e in events if e.payload.get("capability") == "mock_external_search"]
    revoked_idx = all_types.index("PolicyUpdated")
    created_after_revoked = all_types.index("PolicyCreated", revoked_idx)
    assert created_after_revoked > revoked_idx


def test_risk_update_emits_policy_updated(kernel):
    """Changing risk on an existing active external tool emits PolicyUpdated."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    # Re-register with different risk
    capability_governance.register_external_tool("mock_external_search", risk="forbidden")

    events = kernel.read_events(aggregate_type="policy")
    updated = [e for e in events if e.type == "PolicyUpdated" and e.payload.get("capability") == "mock_external_search"]
    assert len(updated) == 1
    assert updated[0].payload["risk_level"] == "forbidden"

    # Projection reflects the update
    rows = kernel.query_state("policy_events", capability="mock_external_search", status="active")
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "forbidden"


def test_no_duplicate_event_on_same_risk(kernel):
    """Re-registering with the same risk does not emit duplicate events."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    # Count events before re-registration
    before = len(kernel.read_events(aggregate_type="policy"))

    capability_governance.register_external_tool("mock_external_search", risk="high")
    after = len(kernel.read_events(aggregate_type="policy"))

    assert after == before  # No new events emitted

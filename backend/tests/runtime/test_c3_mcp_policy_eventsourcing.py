"""C3 · External MCP Policy full event sourcing tests.

Validates:
  1. register_external_tool emits PolicyCreated into event_log
  2. rebuild("policy") recovers external tools from event_log
  3. clear_external_tools(persist=True) emits revoke; default clear does not
  4. Re-registration after durable revoke reactivates via PolicyUpdated
  5. Mesh stop/start cycle (clear without persist) does not flood event_log
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
    """Clean up external tools after each test (in-memory only)."""
    yield
    capability_governance.clear_external_tools()


def test_register_external_tool_emits_policy_created(kernel):
    """register_external_tool emits PolicyCreated into event_log."""
    capability_governance.register_external_tool("mock_external_search", risk="high")

    events = kernel.read_events(aggregate_type="policy")
    created = [
        e for e in events
        if e.type == "PolicyCreated" and e.payload.get("capability") == "mock_external_search"
    ]
    assert len(created) == 1
    assert created[0].payload["risk_level"] == "high"
    assert created[0].actor == "kernel"


def test_rebuild_recovers_external_tool_policy(kernel):
    """rebuild("policy") recovers external tool policy from event_log."""
    capability_governance.register_external_tool("mock_external_search", risk="high")

    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "high"

    kernel.rebuild("policy")

    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "high"


def test_clear_external_tools_default_does_not_revoke(kernel):
    """Process-lifecycle clear must not emit PolicyUpdated(revoked)."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    before = len(kernel.read_events(aggregate_type="policy"))

    capability_governance.clear_external_tools()

    after = len(kernel.read_events(aggregate_type="policy"))
    assert after == before
    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 1
    assert not capability_governance._external_needs_user


def test_clear_external_tools_persist_emits_revoke(kernel):
    """persist=True durably revokes and clears in-memory cache."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.register_external_tool("mock_external_write", risk="forbidden")

    capability_governance.clear_external_tools(persist=True)

    events = kernel.read_events(aggregate_type="policy")
    revoked = [
        e for e in events
        if e.type == "PolicyUpdated" and e.payload.get("status") == "revoked"
    ]
    assert len(revoked) == 2
    capabilities = {e.payload.get("capability") for e in revoked}
    assert capabilities == {"mock_external_search", "mock_external_write"}

    assert not capability_governance._external_auto_allow
    assert not capability_governance._external_needs_user
    assert not capability_governance._external_forbidden


def test_rebuild_after_persist_clear_excludes_revoked(kernel):
    """After persist clear, rebuild must not treat the tool as active."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.clear_external_tools(persist=True)

    kernel.rebuild("policy")

    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 0

    all_rows = kernel.query_state("policy_events", capability="mock_external_search")
    assert len(all_rows) == 1
    assert all_rows[0]["status"] == "revoked"


def test_reregister_after_persist_clear_reactivates(kernel):
    """Re-register after durable revoke reactivates via PolicyUpdated(active)."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.clear_external_tools(persist=True)

    capability_governance.register_external_tool("mock_external_search", risk="low")

    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "low"

    events = [
        e for e in kernel.read_events(aggregate_type="policy")
        if e.payload.get("capability") == "mock_external_search"
    ]
    types = [e.type for e in events]
    assert types.count("PolicyCreated") == 1
    assert any(
        e.type == "PolicyUpdated" and e.payload.get("status") == "revoked"
        for e in events
    )
    assert any(
        e.type == "PolicyUpdated"
        and e.payload.get("status") == "active"
        and e.payload.get("risk_level") == "low"
        for e in events
    )


def test_mesh_restart_cycle_is_idempotent(kernel):
    """Simulate MCP stop/start: clear (no persist) + re-register → no new events."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.register_external_tool("mock_external_browse", risk="low")
    before = len(kernel.read_events(aggregate_type="policy"))

    # mesh.stop()
    capability_governance.clear_external_tools()
    # mesh.start() rediscovery
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.register_external_tool("mock_external_browse", risk="low")

    after = len(kernel.read_events(aggregate_type="policy"))
    assert after == before

    for name, risk in (("mock_external_search", "high"), ("mock_external_browse", "low")):
        created = [
            e for e in kernel.read_events(aggregate_type="policy")
            if e.type == "PolicyCreated" and e.payload.get("capability") == name
        ]
        assert len(created) == 1
        rows = kernel.query_state("policy_events", capability=name, status="active")
        assert len(rows) == 1
        assert rows[0]["risk_level"] == risk


def test_risk_update_emits_policy_updated(kernel):
    """Changing risk on an existing active external tool emits PolicyUpdated."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    capability_governance.register_external_tool("mock_external_search", risk="forbidden")

    events = kernel.read_events(aggregate_type="policy")
    updated = [
        e for e in events
        if e.type == "PolicyUpdated"
        and e.payload.get("capability") == "mock_external_search"
        and e.payload.get("status") is None
    ]
    assert len(updated) == 1
    assert updated[0].payload["risk_level"] == "forbidden"

    rows = kernel.query_state(
        "policy_events", capability="mock_external_search", status="active",
    )
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "forbidden"


def test_no_duplicate_event_on_same_risk(kernel):
    """Re-registering with the same risk does not emit duplicate events."""
    capability_governance.register_external_tool("mock_external_search", risk="high")
    before = len(kernel.read_events(aggregate_type="policy"))

    capability_governance.register_external_tool("mock_external_search", risk="high")
    after = len(kernel.read_events(aggregate_type="policy"))

    assert after == before


def test_revoke_external_tools_selective(kernel):
    """revoke_external_tools only touches named active policies."""
    capability_governance.register_external_tool("keep_me", risk="low")
    capability_governance.register_external_tool("drop_me", risk="high")

    n = capability_governance.revoke_external_tools(["drop_me", "never_existed"])
    assert n == 1

    assert kernel.query_state(
        "policy_events", capability="keep_me", status="active",
    )
    dropped = kernel.query_state("policy_events", capability="drop_me")
    assert dropped[0]["status"] == "revoked"

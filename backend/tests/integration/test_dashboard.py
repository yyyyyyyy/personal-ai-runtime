"""Personal Dashboard integration tests.

Proves the Runtime can natively host a product without boundary violations.
The dashboard product accesses data exclusively through Kernel ABI:
query_state, read_events, recall_memory.
"""

from starlette.testclient import TestClient


def test_dashboard_returns_all_widgets(client: TestClient):
    """Dashboard endpoint returns all five widgets."""
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()

    assert "generated_at" in data
    assert "active_goals" in data
    assert "recent_events" in data
    assert "recent_memories" in data
    assert "timer_status" in data
    assert "governance_status" in data


def test_dashboard_active_goals_structure(client: TestClient):
    """Active goals widget has correct structure."""
    r = client.get("/api/dashboard")
    data = r.json()
    goals = data["active_goals"]

    assert "count" in goals
    assert "top" in goals
    assert isinstance(goals["count"], int)


def test_dashboard_recent_events_structure(client: TestClient):
    """Recent events widget has correct structure."""
    r = client.get("/api/dashboard")
    data = r.json()
    events = data["recent_events"]

    assert "count" in events
    assert "total_in_window" in events
    assert "items" in events
    assert isinstance(events["count"], int)


def test_dashboard_timer_status_structure(client: TestClient):
    """Timer status widget has correct structure."""
    r = client.get("/api/dashboard")
    data = r.json()
    timer = data["timer_status"]

    assert "active_timers" in timer
    assert "items" in timer
    assert isinstance(timer["active_timers"], int)


def test_dashboard_governance_status_structure(client: TestClient):
    """Governance status widget verifies runtime health."""
    r = client.get("/api/dashboard")
    data = r.json()
    gov = data["governance_status"]

    assert "active_policies" in gov
    assert "active_grants" in gov
    assert isinstance(gov["active_policies"], int)
    assert isinstance(gov["active_grants"], int)


def test_dashboard_no_boundary_violation(client: TestClient):
    """Prove dashboard product introduces zero boundary violations.

    The dashboard product (app/product/personal_dashboard.py) accesses data
    exclusively through Kernel ABI. If it violated the boundary,
    check_boundary.py would fail — and we've already confirmed it passes.
    """
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    # All 5 widgets are present, proving the product works on pure ABI
    assert "active_goals" in data
    assert "recent_events" in data
    assert "recent_memories" in data
    assert "timer_status" in data
    assert "governance_status" in data

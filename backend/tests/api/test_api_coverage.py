"""API smoke tests for high-gap endpoints.

Targets the endpoints that contributed most to the <50% API coverage gate.
Uses TestClient with a fresh isolated DB so no real LLM / external services
are needed.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


async def _noop_start() -> int:
    return 0


async def _noop_stop() -> None:
    return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("AUTH_TOKEN", "")

    monkeypatch.setattr("app.core.harness.mcp_lifecycle.start_mcp_mesh", _noop_start)
    monkeypatch.setattr("app.core.harness.mcp_lifecycle.stop_mcp_mesh", _noop_stop)

    from app.store.database import Database
    Database._instance = None

    import app.api.system
    import app.config
    import app.main
    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    yield TestClient(app.main.app)


# ── Memory API ────────────────────────────────────────────────────────────


class TestMemoryAPI:
    def test_list_returns_list(self, client):
        resp = client.get("/api/memory/memories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_list(self, client):
        resp = client.post("/api/memory/memories", json={"content": "likes python", "category": "fact"})
        assert resp.status_code == 200
        mid = resp.json()["id"]

        resp = client.get("/api/memory/memories")
        assert any(m["id"] == mid for m in resp.json())

    def test_create_empty_rejected(self, client):
        resp = client.post("/api/memory/memories", json={"content": ""})
        assert resp.status_code == 400

    def test_delete_not_found(self, client):
        resp = client.delete("/api/memory/memories/nonexistent")
        assert resp.status_code == 404

    def test_update_not_found(self, client):
        resp = client.put("/api/memory/memories/nonexistent", json={"content": "x"})
        assert resp.status_code == 404

    def test_ratify_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/ratify")
        assert resp.status_code == 404

    def test_reject_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/reject")
        assert resp.status_code == 404

    def test_contest_not_found(self, client):
        resp = client.post("/api/memory/memories/nonexistent/contest")
        assert resp.status_code == 404

    def test_search_empty_query_rejected(self, client):
        resp = client.get("/api/memory/memories/search?q=")
        assert resp.status_code == 400

    def test_portrait_returns_structure(self, client):
        resp = client.get("/api/memory/portrait")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "habits" in data
        assert "goals" in data

    def test_graph_returns_structure(self, client):
        resp = client.get("/api/memory/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data and "edges" in data

    def test_memories_grouped(self, client):
        resp = client.get("/api/memory/memories/grouped")
        assert resp.status_code == 200
        assert "memories" in resp.json()


# ── Goals API ─────────────────────────────────────────────────────────────


class TestGoalsAPI:
    def test_list_empty(self, client):
        resp = client.get("/api/goals/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_goal(self, client):
        resp = client.post("/api/goals/", json={"title": "Learn Rust"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "active")

    def test_get_not_found(self, client):
        resp = client.get("/api/goals/nonexistent")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/api/goals/nonexistent")
        assert resp.status_code == 404


# ── Workflows API ─────────────────────────────────────────────────────────


class TestWorkflowsAPI:
    def test_endpoints_present(self, client):
        """Workflows were downgraded from production UI in v0.2.0.
        Verify the module loads without import errors."""
        from app.api import workflows
        assert workflows.router is not None


# ── Approvals API ─────────────────────────────────────────────────────────


class TestApprovalsAPI:
    def test_approve_not_found(self, client):
        resp = client.post("/api/approvals/nonexistent/approve")
        assert resp.status_code == 404

    def test_reject_not_found(self, client):
        resp = client.post("/api/approvals/nonexistent/reject")
        assert resp.status_code == 404


# ── System API ────────────────────────────────────────────────────────────


class TestSystemAPI:
    def test_health(self, client):
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_live(self, client):
        resp = client.get("/api/system/live")
        assert resp.status_code == 200

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "running" in resp.json()["message"].lower()

    def test_info(self, client):
        resp = client.get("/api/system/info")
        assert resp.status_code == 200

    def test_llm_providers(self, client):
        resp = client.get("/api/system/llm-providers")
        assert resp.status_code == 200


# ── Tasks API ─────────────────────────────────────────────────────────────


class TestTasksAPI:
    def test_list(self, client):
        resp = client.get("/api/tasks/")
        assert resp.status_code == 200


# ── Triggers API ──────────────────────────────────────────────────────────


class TestTriggersAPI:
    def test_list(self, client):
        resp = client.get("/api/triggers/")
        assert resp.status_code == 200


# ── Notifications API ─────────────────────────────────────────────────────


class TestNotificationsAPI:
    def test_list(self, client):
        resp = client.get("/api/notifications/")
        assert resp.status_code == 200

    def test_unread_count(self, client):
        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 200


# ── Dashboard API ─────────────────────────────────────────────────────────


class TestDashboardAPI:
    def test_dashboard(self, client):
        resp = client.get("/api/dashboard/")
        assert resp.status_code == 200


# ── Timeline API ──────────────────────────────────────────────────────────


class TestTimelineAPI:
    def test_events(self, client):
        resp = client.get("/api/timeline/events")
        assert resp.status_code == 200


# ── Telemetry API ─────────────────────────────────────────────────────────


class TestTelemetryAPI:
    def test_cost_summary(self, client):
        resp = client.get("/api/telemetry/cost/summary")
        assert resp.status_code == 200

    def test_tool_summary(self, client):
        resp = client.get("/api/telemetry/tool-summary")
        assert resp.status_code == 200

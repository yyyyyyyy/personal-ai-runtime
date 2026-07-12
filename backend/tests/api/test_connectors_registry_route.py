"""Regression: static connector routes must beat /{connector_name}."""

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

    import app.api.system
    import app.config
    import app.main

    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    with TestClient(app.main.app) as c:
        yield c


def test_connectors_registry_not_captured_as_connector_name(client):
    """GET /api/connectors/registry must hit list_registry, not get_connector."""
    r = client.get("/api/connectors/registry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "servers" in body
    assert "total" in body
    assert "detail" not in body or "not found" not in str(body.get("detail", "")).lower()


def test_connectors_named_lookup_still_works(client):
    r = client.get("/api/connectors/mail")
    assert r.status_code == 200
    assert r.json()["name"] == "mail"

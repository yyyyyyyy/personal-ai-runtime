"""Shared fixtures for HTTP integration tests."""

import importlib

import pytest
from fastapi.testclient import TestClient


async def _noop_start_mcp_mesh() -> int:
    return 0


async def _noop_stop_mcp_mesh() -> None:
    return None


def _make_client(tmp_path, monkeypatch, auth_token: str | None = None):
    db_path = str(tmp_path / "api_test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    # Explicit empty string overrides AUTH_TOKEN from .env on disk
    monkeypatch.setenv("AUTH_TOKEN", auth_token or "")

    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.start_mcp_mesh",
        _noop_start_mcp_mesh,
    )
    monkeypatch.setattr(
        "app.core.harness.mcp_lifecycle.stop_mcp_mesh",
        _noop_stop_mcp_mesh,
    )

    from app.store.database import Database

    Database._instance = None

    import app.api.system
    import app.config
    import app.main
    from app.core.startup_health import enrich_with_mcp_status, run_startup_checks

    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    app = app.main.app
    app.state.startup_health = enrich_with_mcp_status(run_startup_checks())

    yield TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    yield from _make_client(tmp_path, monkeypatch)


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    yield from _make_client(tmp_path, monkeypatch, auth_token="test-secret")

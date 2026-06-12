"""Shared fixtures for HTTP integration tests."""

import importlib

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch, auth_token: str | None = None) -> TestClient:
    db_path = str(tmp_path / "api_test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    # Explicit empty string overrides AUTH_TOKEN from .env on disk
    monkeypatch.setenv("AUTH_TOKEN", auth_token or "")

    from app.store.database import Database

    Database._instance = None

    import app.api.system
    import app.config
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    return TestClient(app.main.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return _make_client(tmp_path, monkeypatch)


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    return _make_client(tmp_path, monkeypatch, auth_token="test-secret")

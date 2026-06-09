"""Integration test: Goals API via TestClient."""

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "api_test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))

    from app.store.database import Database
    Database._instance = None

    from app.main import app
    return TestClient(app)


def test_create_and_list_goals(client):
    r = client.post("/api/goals/", json={"title": "Test Goal", "importance": 0.8})
    assert r.status_code == 200
    goal = r.json()
    assert goal["title"] == "Test Goal"

    r2 = client.get("/api/goals/")
    assert r2.status_code == 200
    assert any(g["title"] == "Test Goal" for g in r2.json())

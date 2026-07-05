"""Tests for /api/work-items endpoints (v1.0 Phase 3a)."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated TestClient with fresh Kernel + DB."""
    db_path = str(tmp_path / "work_items_api.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VECTOR_DIR", str(tmp_path / "vectors"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("AUTH_TOKEN", "")

    async def _noop_start():
        return 0

    async def _noop_stop():
        return None

    monkeypatch.setattr("app.core.harness.mcp_lifecycle.start_mcp_mesh", _noop_start)
    monkeypatch.setattr("app.core.harness.mcp_lifecycle.stop_mcp_mesh", _noop_stop)

    from app.store.database import Database

    Database._instance = None

    import importlib

    import app.api.system
    import app.config
    import app.main

    app.config.reset_settings()
    importlib.reload(app.api.system)
    importlib.reload(app.main)

    app_obj = app.main.app
    yield TestClient(app_obj)


def test_create_goal_work_item(client):
    """POST /api/work-items/ with work_type='goal' persists goal fields."""
    r = client.post("/api/work-items/", json={
        "title": "Run a marathon",
        "work_type": "goal",
        "progress": 0.0,
        "importance": 0.9,
        "urgency": 0.4,
        "deadline": "2026-12-01T00:00:00Z",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["work_type"] == "goal"
    assert body["title"] == "Run a marathon"
    assert body["progress"] == 0.0
    assert body["importance"] == 0.9
    assert body["urgency"] == 0.4
    assert body["deadline"] == "2026-12-01T00:00:00Z"


def test_create_task_work_item_uses_defaults(client):
    """POST /api/work-items/ with work_type='task' gets defaults for goal fields."""
    r = client.post("/api/work-items/", json={
        "title": "Ship feature",
        "work_type": "task",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["work_type"] == "task"
    # Defaults from schema
    assert body["progress"] == 0
    assert body["importance"] == 0.5
    assert body["urgency"] == 0.5
    assert body["deadline"] is None


def test_create_invalid_work_type_rejected(client):
    """Invalid work_type returns 400."""
    r = client.post("/api/work-items/", json={
        "title": "X",
        "work_type": "invalid_type",
    })
    assert r.status_code == 400


def test_list_filter_by_work_type(client):
    """GET /api/work-items/?work_type=goal returns only goal rows."""
    client.post("/api/work-items/", json={"title": "Goal A", "work_type": "goal"})
    client.post("/api/work-items/", json={"title": "Task A", "work_type": "task"})
    client.post("/api/work-items/", json={"title": "Goal B", "work_type": "goal"})

    r = client.get("/api/work-items/?work_type=goal")
    assert r.status_code == 200
    titles = [item["title"] for item in r.json()]
    assert "Goal A" in titles
    assert "Goal B" in titles
    assert "Task A" not in titles


def test_patch_updates_goal_fields(client):
    """PATCH /api/work-items/{id} can update progress/deadline/etc."""
    create = client.post("/api/work-items/", json={
        "title": "Write book",
        "work_type": "goal",
        "progress": 0.0,
    })
    item_id = create.json()["id"]

    r = client.patch(f"/api/work-items/{item_id}", json={
        "progress": 0.5,
        "urgency": 0.8,
        "deadline": "2026-11-01T00:00:00Z",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["progress"] == 0.5
    assert body["urgency"] == 0.8
    assert body["deadline"] == "2026-11-01T00:00:00Z"


def test_patch_404_on_missing_item(client):
    r = client.patch("/api/work-items/nonexistent", json={"title": "X"})
    assert r.status_code == 404


def test_status_transition(client):
    """POST /{id}/status transitions state machine."""
    create = client.post("/api/work-items/", json={
        "title": "T", "work_type": "task",
    })
    item_id = create.json()["id"]

    r = client.post(f"/api/work-items/{item_id}/status", json={"status": "running"})
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_get_children(client):
    """GET /{id}/children returns direct sub-items."""
    parent = client.post("/api/work-items/", json={
        "title": "Parent goal", "work_type": "goal",
    })
    parent_id = parent.json()["id"]
    client.post("/api/work-items/", json={
        "title": "Child 1", "work_type": "task", "parent_work_id": parent_id,
    })
    client.post("/api/work-items/", json={
        "title": "Child 2", "work_type": "task", "parent_work_id": parent_id,
    })

    r = client.get(f"/api/work-items/{parent_id}/children")
    assert r.status_code == 200
    titles = [item["title"] for item in r.json()]
    assert "Child 1" in titles
    assert "Child 2" in titles


def test_delete(client):
    """DELETE removes the work item."""
    create = client.post("/api/work-items/", json={"title": "X", "work_type": "task"})
    item_id = create.json()["id"]

    r = client.delete(f"/api/work-items/{item_id}")
    assert r.status_code == 200

    # Subsequent GET should 404
    assert client.get(f"/api/work-items/{item_id}").status_code == 404

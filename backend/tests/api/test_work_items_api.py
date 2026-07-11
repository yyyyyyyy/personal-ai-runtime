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


# ── Phase 4 new capabilities: include=, cascade delete, decompose, side-effects ─


def test_get_with_include_actions_events(client):
    """GET /{id}?include=actions,events embeds child actions and recent events."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]
    client.post("/api/work-items/", json={
        "title": "A1", "work_type": "action", "parent_goal_id": gid,
    })

    r = client.get(f"/api/work-items/{gid}?include=actions,events")
    assert r.status_code == 200
    body = r.json()
    assert len(body["actions"]) == 1
    assert body["actions"][0]["title"] == "A1"
    assert isinstance(body["events"], list)


def test_get_with_include_tree(client):
    """GET /{id}?include=tree returns the nested work item tree for goals."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]
    client.post("/api/work-items/", json={
        "title": "Child", "work_type": "task", "parent_goal_id": gid,
    })

    r = client.get(f"/api/work-items/{gid}?include=tree")
    assert r.status_code == 200
    body = r.json()
    assert "tree" in body
    assert isinstance(body["tree"], list)
    assert any(item["title"] == "Child" for item in body["tree"])


def test_get_events_endpoint(client):
    """GET /{id}/events returns UI-shaped event rows for the goal."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]

    r = client.get(f"/api/work-items/{gid}/events")
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    # goal_events aggregates work_item + action + goal events touching this id;
    # WorkItemCreated is emitted on aggregate_type=work_item, so it surfaces.
    assert len(events) >= 1


def test_goal_delete_cascades_children(client):
    """DELETE on a goal cascades to child actions/tasks."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]
    child = client.post("/api/work-items/", json={
        "title": "A1", "work_type": "action", "parent_goal_id": gid,
    })
    child_id = child.json()["id"]

    r = client.delete(f"/api/work-items/{gid}")
    assert r.status_code == 200
    assert client.get(f"/api/work-items/{gid}").status_code == 404
    assert client.get(f"/api/work-items/{child_id}").status_code == 404


def test_task_delete_does_not_cascade(client):
    """DELETE on a non-goal work item only removes itself."""
    parent = client.post("/api/work-items/", json={"title": "P", "work_type": "task"})
    pid = parent.json()["id"]
    child = client.post("/api/work-items/", json={
        "title": "C", "work_type": "task", "parent_work_id": pid,
    })
    cid = child.json()["id"]

    r = client.delete(f"/api/work-items/{pid}")
    assert r.status_code == 200
    assert client.get(f"/api/work-items/{pid}").status_code == 404
    # Child linked via parent_work_id is NOT cascaded (only goals cascade).
    assert client.get(f"/api/work-items/{cid}").status_code == 200


def test_action_completion_bumps_parent_activity(client):
    """Completing an action bumps the parent goal's last_activity_at."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]
    before = goal.json().get("last_activity_at")

    action = client.post("/api/work-items/", json={
        "title": "A", "work_type": "action", "parent_goal_id": gid,
    })
    aid = action.json()["id"]

    r = client.patch(f"/api/work-items/{aid}", json={"status": "completed"})
    assert r.status_code == 200

    updated_goal = client.get(f"/api/work-items/{gid}").json()
    after = updated_goal.get("last_activity_at")
    assert after is not None
    if before is not None:
        assert after >= before


def test_goal_status_via_status_endpoint(client):
    """POST /{id}/status with goal status updates via WorkItemUpdated path."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]

    r = client.post(f"/api/work-items/{gid}/status", json={"status": "paused"})
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    r2 = client.post(f"/api/work-items/{gid}/status", json={"status": "completed"})
    assert r2.status_code == 200


def test_decompose_rejects_non_goal(client):
    """POST /{id}/decompose returns 400 for non-goal work items."""
    task = client.post("/api/work-items/", json={"title": "T", "work_type": "task"})
    tid = task.json()["id"]

    r = client.post(f"/api/work-items/{tid}/decompose")
    assert r.status_code == 400


def test_decompose_not_found(client):
    """POST /{id}/decompose returns 404 for missing work item."""
    r = client.post("/api/work-items/nonexistent/decompose")
    assert r.status_code == 404


def test_list_filters_by_parent_goal_id(client):
    """GET /?parent_goal_id=X filters children of a goal."""
    goal = client.post("/api/work-items/", json={"title": "G", "work_type": "goal"})
    gid = goal.json()["id"]
    client.post("/api/work-items/", json={
        "title": "A1", "work_type": "action", "parent_goal_id": gid,
    })
    client.post("/api/work-items/", json={
        "title": "Other", "work_type": "task",
    })

    r = client.get(f"/api/work-items/?parent_goal_id={gid}")
    assert r.status_code == 200
    titles = [item["title"] for item in r.json()]
    assert "A1" in titles
    assert "Other" not in titles


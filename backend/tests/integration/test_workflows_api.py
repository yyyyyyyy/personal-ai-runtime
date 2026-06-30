"""Integration tests for Workflow API — CRUD, export, palette.

Downgraded in v0.2: Workflow router is no longer registered in main.py.
Tests are preserved but skipped pending decision to restore the feature.
"""
import pytest
from starlette.testclient import TestClient

pytestmark = pytest.mark.skip(reason="Workflow router downgraded in v0.2 — API not registered")


def test_node_palette(client: TestClient):
    r = client.get("/api/workflows/_palette")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert len(data["nodes"]) == 5
    types = {n["type"] for n in data["nodes"]}
    assert "schedule" in types
    assert "trigger" in types
    assert "agent" in types
    assert "action" in types
    assert "notification" in types


def test_create_workflow(client: TestClient):
    r = client.post("/api/workflows", json={
        "name": "Test Workflow",
        "description": "A test",
        "nodes": [{"id": "n1", "type": "schedule", "label": "Timer", "x": 0, "y": 0, "data": {"schedule": "0 8 * * *"}}],
        "edges": [],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Test Workflow"
    assert data["id"]
    assert data["nodes"][0]["id"] == "n1"


def test_list_workflows(client: TestClient):
    # Create one first
    client.post("/api/workflows", json={"name": "WF1", "nodes": [], "edges": []})
    client.post("/api/workflows", json={"name": "WF2", "nodes": [], "edges": []})
    r = client.get("/api/workflows")
    assert r.status_code == 200
    data = r.json()
    assert len(data["workflows"]) >= 2


def test_update_workflow(client: TestClient):
    r = client.post("/api/workflows", json={"name": "Old Name", "nodes": [], "edges": []})
    wf_id = r.json()["id"]
    r = client.put(f"/api/workflows/{wf_id}", json={"name": "New Name", "enabled": True})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    assert r.json()["enabled"] is True


def test_delete_workflow(client: TestClient):
    r = client.post("/api/workflows", json={"name": "To Delete", "nodes": [], "edges": []})
    wf_id = r.json()["id"]
    r = client.delete(f"/api/workflows/{wf_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Verify deleted
    r = client.put(f"/api/workflows/{wf_id}", json={"name": "X"})
    assert r.status_code == 404


def test_workflow_not_found(client: TestClient):
    r = client.get("/api/workflows/nonexistent/export")
    assert r.status_code == 404
    r = client.put("/api/workflows/nonexistent", json={"name": "X"})
    assert r.status_code == 404
    r = client.delete("/api/workflows/nonexistent")
    assert r.status_code == 404


def test_export_executable_plan(client: TestClient):
    nodes = [
        {"id": "s1", "type": "schedule", "label": "Morning", "x": 0, "y": 0, "data": {"schedule": "0 8 * * *"}},
        {"id": "a1", "type": "agent", "label": "Chat", "x": 200, "y": 0, "data": {"prompt": "Summarize"}},
        {"id": "act1", "type": "action", "label": "Notify", "x": 400, "y": 0, "data": {"tool": "web_search", "params": {"q": "news"}}},
    ]
    edges = [
        {"id": "e1", "source": "s1", "target": "a1"},
        {"id": "e2", "source": "a1", "target": "act1"},
    ]
    r = client.post("/api/workflows", json={"name": "Morning Brief", "nodes": nodes, "edges": edges})
    wf_id = r.json()["id"]

    r = client.get(f"/api/workflows/{wf_id}/export")
    assert r.status_code == 200
    data = r.json()
    plan = data["plan"]
    assert "steps" in plan
    assert len(plan["steps"]) == 3
    assert plan["steps"][0]["trigger"]["type"] == "schedule"
    assert plan["steps"][1]["tool"] == "chat"
    assert plan["steps"][2]["tool"] == "web_search"

def test_export_empty_workflow(client: TestClient):
    r = client.post("/api/workflows", json={"name": "Empty", "nodes": [], "edges": []})
    wf_id = r.json()["id"]
    r = client.get(f"/api/workflows/{wf_id}/export")
    assert r.status_code == 200
    plan = r.json()["plan"]
    assert plan["steps"] == []


def test_export_complex_topology(client: TestClient):
    """Test export handles: trigger->agent->action->notification chain."""
    nodes = [
        {"id": "t1", "type": "trigger", "label": "Email Received", "x": 0, "y": 0, "data": {"event": "inbox_email"}},
        {"id": "a1", "type": "agent", "label": "Analyze", "x": 200, "y": 0, "data": {"prompt": "Analyze"}},
        {"id": "act1", "type": "action", "label": "Search", "x": 400, "y": 0, "data": {"tool": "web_search"}},
        {"id": "n1", "type": "notification", "label": "Alert", "x": 600, "y": 0, "data": {"title": "Done"}},
    ]
    edges = [
        {"id": "e1", "source": "t1", "target": "a1"},
        {"id": "e2", "source": "a1", "target": "act1"},
        {"id": "e3", "source": "act1", "target": "n1"},
    ]
    r = client.post("/api/workflows", json={"name": "Chain", "nodes": nodes, "edges": edges})
    wf_id = r.json()["id"]
    r = client.get(f"/api/workflows/{wf_id}/export")
    assert r.status_code == 200
    plan = r.json()["plan"]
    assert len(plan["steps"]) == 4


def test_scene_templates_separate_nodes_and_edges(client: TestClient):
    """Templates must define nodes and edges as distinct arrays.

    Regression guard: an earlier version inlined edges into the nodes array,
    which made export_executable_plan treat pseudo 'edge' entries as nodes.
    """
    from app.api.workflows import SCENE_TEMPLATES

    for tpl in SCENE_TEMPLATES:
        node_ids = {n["id"] for n in tpl["nodes"]}
        edges = tpl.get("edges", [])
        # No node should be an edge in disguise.
        for e in edges:
            assert e["id"] not in node_ids, (
                f"Template {tpl['id']} has edge {e['id']} masquerading as a node"
            )
            assert e["source"] in node_ids, (
                f"Template {tpl['id']} edge {e['id']} references missing source {e['source']}"
            )
            assert e["target"] in node_ids, (
                f"Template {tpl['id']} edge {e['id']} references missing target {e['target']}"
            )

    # Instantiating a template should produce a valid export.
    r = client.post("/api/workflows/from-template/template-inbox")
    assert r.status_code == 200
    wf_id = r.json()["id"]
    r = client.get(f"/api/workflows/{wf_id}/export")
    assert r.status_code == 200
    plan = r.json()["plan"]
    # Inbox template: schedule + check_inbox + agent + notification = 4 steps,
    # NOT 7 (which it would be if edges were counted as nodes).
    assert len(plan["steps"]) == 4


def test_workflow_mutations_emit_audit_event(client: TestClient):
    """create/update/delete must emit WorkflowChanged audit events to event_log."""
    from app.core.runtime.kernel_instance import kernel

    before = len(kernel.read_events(type="WorkflowChanged"))

    r = client.post("/api/workflows", json={"name": "Audit Test", "nodes": [], "edges": []})
    wf_id = r.json()["id"]
    after_create = len(kernel.read_events(type="WorkflowChanged"))
    assert after_create == before + 1, "create did not emit audit event"

    client.put(f"/api/workflows/{wf_id}", json={"name": "Renamed"})
    after_update = len(kernel.read_events(type="WorkflowChanged"))
    assert after_update == after_create + 1, "update did not emit audit event"

    client.delete(f"/api/workflows/{wf_id}")
    after_delete = len(kernel.read_events(type="WorkflowChanged"))
    assert after_delete == after_update + 1, "delete did not emit audit event"

    # Verify the create event payload.
    create_events = kernel.read_events(type="WorkflowChanged")
    last = create_events[-1]
    assert last.payload["action"] == "deleted"
    assert last.payload["workflow_id"] == wf_id

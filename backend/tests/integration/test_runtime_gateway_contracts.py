"""HTTP contract smoke tests for Runtime Gateway tool backends."""

from fastapi.testclient import TestClient


def test_knowledge_search_is_get_with_results(client: TestClient):
    r = client.get("/api/knowledge/search", params={"query": "gateway", "n_results": 1})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], list)


def test_memory_search_returns_list(client: TestClient):
    r = client.get("/api/memory/memories/search", params={"q": "gateway", "n": 1})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_timeline_events_shape(client: TestClient):
    r = client.get("/api/timeline/events", params={"page": 1, "page_size": 5})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_approvals_pending_enriched_honours_limit(client: TestClient, monkeypatch):
    rows = [
        {"id": f"a{i}", "action": "shell_exec", "task_id": None}
        for i in range(5)
    ]
    monkeypatch.setattr(
        "app.api.approvals.read_ports.query_pending_approvals",
        lambda: rows,
    )
    monkeypatch.setattr(
        "app.api.approvals.kernel.read_events",
        lambda **kwargs: [],
    )
    r = client.get(
        "/api/approvals/",
        params={"pending_only": True, "enriched": True, "limit": 2},
    )
    assert r.status_code == 200
    assert len(r.json()) == 2

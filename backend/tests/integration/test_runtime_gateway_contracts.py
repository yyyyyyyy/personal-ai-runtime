"""Runtime Gateway HTTP contracts that are not covered by api smoke.

Keeps knowledge search (absent from api coverage) and approvals ``limit``
behavior; memory/timeline shapes live in api/timeline integration suites.
"""

from fastapi.testclient import TestClient


def test_knowledge_search_is_get_with_results(client: TestClient):
    r = client.get("/api/knowledge/search", params={"query": "gateway", "n_results": 1})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], list)


def test_approvals_pending_enriched_honours_limit(client: TestClient, monkeypatch):
    rows = [
        {"id": f"a{i}", "action": "shell_exec", "task_id": None}
        for i in range(5)
    ]
    monkeypatch.setattr(
        "app.api.approvals.read_ports.query_pending_approvals",
        lambda: rows,
    )
    # Patch the Kernel class — not ``approvals.kernel.read_events``.
    # setattr on the shared ``_LazyProxy`` sticks a bound method on the proxy
    # after monkeypatch undo and poisons later tests that call read_events.
    monkeypatch.setattr(
        "app.core.runtime.kernel.kernel.Kernel.read_events",
        lambda self, **kwargs: [],
    )
    r = client.get(
        "/api/approvals/",
        params={"pending_only": True, "enriched": True, "limit": 2},
    )
    assert r.status_code == 200
    assert len(r.json()) == 2

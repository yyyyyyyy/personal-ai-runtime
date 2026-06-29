"""Integration tests for Timeline API."""
from starlette.testclient import TestClient


def test_timeline_events_empty(client: TestClient):
    r = client.get("/api/timeline/events")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_timeline_events_pagination(client: TestClient):
    r = client.get("/api/timeline/events?page=1&page_size=2")
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_timeline_events_filter_by_type(client: TestClient):
    r = client.get("/api/timeline/events?event_type=GoalCreated")
    assert r.status_code == 200
    data = r.json()
    for item in data["items"]:
        assert item["type"] == "GoalCreated"


def test_timeline_events_date_filter(client: TestClient):
    r = client.get("/api/timeline/events?date_from=2026-01-01&date_to=2026-12-31")
    assert r.status_code == 200

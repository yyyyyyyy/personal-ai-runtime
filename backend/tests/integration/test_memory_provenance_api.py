"""Integration tests for Memory provenance API (Phase 2.1).

Verifies that GET /api/memory/memories/{id}/provenance returns the full
event chain for a memory, enabling the "explainable memory" UI.
"""


from starlette.testclient import TestClient


def test_provenance_returns_event_chain(client: TestClient):
    # Create a memory via the API
    create = client.post("/api/memory/memories", json={"content": "I love Rust", "category": "preference"})
    assert create.status_code == 200
    mem_id = create.json()["id"]

    # Fetch provenance
    r = client.get(f"/api/memory/memories/{mem_id}/provenance")
    assert r.status_code == 200
    data = r.json()
    assert data["memory_id"] == mem_id
    events = data["events"]
    assert len(events) >= 1
    # The first event should be MemoryDerived
    assert events[0]["type"] == "MemoryDerived"
    assert events[0]["payload"]["content"] == "I love Rust"
    assert "ts" in events[0]
    assert "actor" in events[0]


def test_provenance_includes_updates(client: TestClient):
    create = client.post("/api/memory/memories", json={"content": "Original content"})
    mem_id = create.json()["id"]

    # Update the memory — appends a MemoryUpdated event
    client.put(f"/api/memory/memories/{mem_id}", json={"content": "Updated content"})

    r = client.get(f"/api/memory/memories/{mem_id}/provenance")
    events = r.json()["events"]
    types = [e["type"] for e in events]
    assert "MemoryDerived" in types
    assert "MemoryUpdated" in types
    # Derived comes before Updated (chronological order)
    assert types.index("MemoryDerived") < types.index("MemoryUpdated")


def test_provenance_404_for_missing(client: TestClient):
    r = client.get("/api/memory/memories/nonexistent-id/provenance")
    assert r.status_code == 404


def test_provenance_preserves_correlation_id(client: TestClient):
    """correlation_id links a memory back to the conversation that produced it."""
    create = client.post("/api/memory/memories", json={"content": "linked fact"})
    mem_id = create.json()["id"]

    r = client.get(f"/api/memory/memories/{mem_id}/provenance")
    events = r.json()["events"]
    # Every event has a correlation_id field (may be None for manual creation)
    for evt in events:
        assert "correlation_id" in evt

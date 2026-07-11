"""Integration test: Goals via work-items API."""

def test_create_and_list_goals(client):
    r = client.post("/api/work-items/", json={
        "title": "Test Goal", "work_type": "goal", "importance": 0.8,
    })
    assert r.status_code == 200
    goal = r.json()
    assert goal["title"] == "Test Goal"

    r2 = client.get("/api/work-items/?work_type=goal")
    assert r2.status_code == 200
    assert any(g["title"] == "Test Goal" for g in r2.json())

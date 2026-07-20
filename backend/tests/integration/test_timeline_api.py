"""Integration tests for Timeline API — deep paths beyond api smoke."""

from fastapi.testclient import TestClient

from app.core.runtime.kernel_instance import kernel


def test_timeline_events_filter_goal_alias(client: TestClient):
    """Legacy GoalCreated filter maps to WorkItemCreated timeline rows."""
    r = client.get("/api/timeline/events?event_type=GoalCreated")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    for item in data["items"]:
        assert item["type"] == "WorkItemCreated"


def test_timeline_pagination_beyond_500(client: TestClient):
    """SQL offset pagination must remain correct past the old 500-row hard cap."""
    probe_type = "TimelinePaginationProbe"
    for i in range(520):
        kernel.emit_event(
            probe_type,
            "probe",
            f"tl_page_{i}",
            payload={"i": i},
        )

    total_count = len(kernel.read_events(type=probe_type, limit=2000))
    assert total_count == 520

    page_size = 30
    deep_page = (500 // page_size) + 2  # page 18 → offset 510
    sql_offset = (deep_page - 1) * page_size
    assert sql_offset > 500

    direct = kernel.read_events(
        type=probe_type,
        limit=page_size,
        offset=sql_offset,
        order="desc",
    )
    assert len(direct) == 520 - sql_offset  # 10

    r = client.get(
        f"/api/timeline/events?page={deep_page}&page_size={page_size}"
        f"&event_type={probe_type}"
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 10
    assert data["has_more"] is False
    assert [item["id"] for item in data["items"]] == [e.id for e in direct]

    r1 = client.get(
        f"/api/timeline/events?page=1&page_size={page_size}&event_type={probe_type}"
    )
    assert r1.json()["has_more"] is True
    assert len(r1.json()["items"]) == page_size
    assert r1.json()["items"][0]["id"] != data["items"][0]["id"]


def test_timeline_message_appended_label(client: TestClient):
    kernel.emit_event(
        "ConversationCreated",
        "conversation",
        "tl_msg_1",
        payload={"title": "t"},
    )
    kernel.emit_event(
        "MessageAppended",
        "conversation",
        "tl_msg_1",
        payload={"role": "user", "content": "hi"},
    )
    r = client.get("/api/timeline/events?event_type=MessageAppended&page_size=5")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert items[0]["description"] == "发送了消息"

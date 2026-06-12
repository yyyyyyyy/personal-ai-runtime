"""Integration: conversation events come from kernel ConversationRecorded only."""


def test_conversation_type_reads_from_kernel(client):
    from app.core.runtime.conversation_recorder import record_conversation_turn

    record_conversation_turn("conv-api-1", "你好", "你好呀")

    r = client.get("/api/events/", params={"type": "conversation", "days": 7, "limit": 20})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row["type"] == "conversation" for row in rows)
    assert any("你好" in (row.get("summary") or "") for row in rows)


def test_legacy_events_table_conversation_not_merged(client):
    from app.core.runtime.conversation_recorder import record_conversation_turn
    from app.core.telemetry.event_recorder import Event, event_recorder

    record_conversation_turn("conv-api-2", "kernel消息", "回复")
    event_recorder.record(
        Event(type="conversation", summary="legacy duplicate", payload={"conversation_id": "old"})
    )

    r = client.get("/api/events/", params={"days": 7, "limit": 50})
    assert r.status_code == 200
    summaries = [row.get("summary") or "" for row in r.json()]
    assert any("kernel消息" in s for s in summaries)
    assert not any("legacy duplicate" in s for s in summaries)

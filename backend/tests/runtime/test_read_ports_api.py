"""Read-port helpers used by API / product layers."""

import pytest

from app.core.runtime import read_ports
from app.core.runtime.reaction_registry import reset_reactions

@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    reset_reactions()
    yield k
    reset_reactions()

def test_query_goal_and_actions(kernel):
    kernel.emit_event(
        "WorkItemCreated", "work_item", "g1",
        payload={"title": "Ship", "work_type": "goal", "status": "active"},
        actor="user",
    )
    kernel.emit_event(
        "WorkItemCreated", "work_item", "a1",
        payload={
            "title": "Step",
            "work_type": "action",
            "parent_goal_id": "g1",
            "status": "pending",
        },
        actor="user",
    )

    goal = read_ports.query_goal("g1")
    assert goal is not None
    assert goal["title"] == "Ship"
    actions = read_ports.query_goal_actions("g1")
    assert len(actions) == 1
    assert actions[0]["id"] == "a1"
    assert read_ports.query_goals(status="active")[0]["id"] == "g1"
    top = read_ports.query_top_active_goals(limit=5)
    assert len(top) == 1
    assert top[0]["title"] == "Ship"

def test_query_memory_and_notifications(kernel):
    kernel.emit_event(
        "MemoryDerived", "memory", "m1",
        payload={"content": "likes tea", "category": "preference", "source": "test"},
        actor="user",
    )
    mem = read_ports.query_memory("m1")
    assert mem is not None
    assert "tea" in mem["content"]

    kernel.emit_event(
        "NotificationCreated", "notification", "n1",
        payload={
            "type": "suggestion",
            "title": "hi",
            "content": "body",
            "severity": "info",
        },
        actor="system",
    )
    notif = read_ports.query_notification("n1")
    assert notif is not None
    assert notif["title"] == "hi"

def test_query_inbox_email(kernel):
    kernel.emit_event(
        "InboxEmailRecorded", "inbox_email", "e1",
        payload={"sender": "a@b.com", "subject": "Hello"},
        actor="inbox",
    )
    row = read_ports.query_inbox_email("e1")
    assert row is not None
    assert row["subject"] == "Hello"
    pending = read_ports.query_pending_inbox_emails(limit=10)
    assert any(r["id"] == "e1" for r in pending)

def test_query_conversation_and_profile(kernel):
    kernel.emit_event(
        "ConversationCreated", "conversation", "c1",
        payload={"title": "Hello", "created_at": "2026-07-11T00:00:00Z"},
        actor="user",
    )
    conv = read_ports.query_conversation("c1")
    assert conv is not None
    assert conv["title"] == "Hello"
    assert read_ports.query_conversations(limit=10)[0]["id"] == "c1"

    kernel.emit_event(
        "UserProfileUpdated", "user_profile", "preferences",
        payload={
            "category": "preferences",
            "data_json": '{"tea": true}',
            "confidence": 0.8,
        },
        actor="user",
    )
    profile = read_ports.query_user_profile_category("preferences")
    assert profile is not None
    assert profile["category"] == "preferences"

def test_pending_inbox_count_exact(kernel):
    for i in range(12):
        kernel.emit_event(
            "InboxEmailRecorded",
            "inbox_email",
            f"mail-{i}",
            payload={"sender": f"a{i}@b.com", "subject": f"s{i}"},
            actor="inbox",
        )
    listed = read_ports.query_pending_inbox_emails(limit=5)
    assert len(listed) == 5
    assert read_ports.count_pending_inbox_emails() == 12

def test_count_active_timers_and_policies(kernel):
    kernel.emit_event(
        "TimerCreated",
        "timer",
        "tm-count",
        payload={
            "handler_name": "x",
            "schedule_type": "once",
            "fire_at": "2099-01-01T00:00:00Z",
        },
        actor="system",
    )
    kernel.emit_event(
        "PolicyCreated",
        "policy",
        "pol-count",
        payload={"capability": "read_file", "risk_level": "low"},
        actor="system",
    )
    assert read_ports.count_active_timers() >= 1
    assert read_ports.count_active_policies() >= 1

def test_unread_notification_count_exact_beyond_list_limit(kernel):
    """COUNT must not be capped by the list query's default LIMIT."""
    for i in range(55):
        kernel.emit_event(
            "NotificationCreated",
            "notification",
            f"n-{i}",
            payload={"type": "info", "title": f"t{i}", "content": "c"},
            actor="system",
        )
    listed = read_ports.query_notifications(unread_only=True, limit=50)
    assert len(listed) == 50
    assert read_ports.query_unread_notification_count() == 55

def test_query_message_by_id(kernel):
    kernel.emit_event(
        "ConversationCreated",
        "conversation",
        "c-msg",
        payload={"title": "Chat"},
        actor="user",
    )
    kernel.emit_event(
        "MessageAppended",
        "conversation",
        "c-msg",
        payload={"message_id": "m-42", "role": "user", "content": "ping"},
        actor="user",
    )
    row = read_ports.query_message("m-42")
    assert row is not None
    assert row["content"] == "ping"
    assert row["conversation_id"] == "c-msg"

def test_timers_and_profile_via_query_state(kernel):
    kernel.emit_event(
        "TimerCreated",
        "timer",
        "tm-1",
        payload={
            "handler_name": "test_timer",
            "schedule_type": "once",
            "fire_at": "2099-01-01T00:00:00Z",
        },
        actor="system",
    )
    assert read_ports.query_timer("tm-1") is not None
    active = read_ports.query_active_timers(limit=10)
    assert any(r["id"] == "tm-1" for r in active)

    kernel.emit_event(
        "UserProfileUpdated",
        "user_profile",
        "style",
        payload={"category": "style", "data_json": '{"tone": "calm"}', "confidence": 0.9},
        actor="user",
    )
    assert read_ports.query_user_profile_category("style")["category"] == "style"

def test_pending_approval_count_exact_beyond_list_limit(kernel):
    """COUNT must not be capped by the list query's default LIMIT 50."""
    for i in range(55):
        kernel.emit_event(
            "ApprovalRequested",
            "approval",
            f"app-{i}",
            payload={"action": "shell_exec", "risk": "high", "ctx": {}},
            actor="agent:test",
        )
    listed = read_ports.query_pending_approvals(limit=50)
    assert len(listed) == 50
    assert read_ports.query_pending_approval_count() == 55
    assert kernel.count_state("approvals", status="pending") == 55

def test_get_mcp_server_status_uses_public_api(monkeypatch):
    """read_ports must not depend on mcp_mesh._connections."""
    calls: list[str | None] = []

    class FakeMesh:
        def get_server_status(self, server_name=None):
            calls.append(server_name)
            return {
                "name": server_name,
                "status": "connected",
                "connected": True,
                "tool_count": 3,
            }

        def list_server_tools(self, server_name):
            return [{"name": "t1", "description": "d"}]

    monkeypatch.setattr("app.core.harness.mcp_mesh.mcp_mesh", FakeMesh())
    status = read_ports.get_mcp_server_status("email")
    assert status == {"connected": True, "tool_count": 3, "status": "connected"}
    assert calls == ["email"]
    tools = read_ports.get_mcp_server_tools("email")
    assert tools == [{"name": "t1", "description": "d"}]


def test_query_top_active_goals_delegates_status_in(monkeypatch):
    calls: list[tuple] = []

    class FakeKernel:
        def query_state(self, selector: str, **filters):
            calls.append((selector, filters))
            return [{"title": "Test Goal", "status": "active"}]

    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", FakeKernel())
    rows = read_ports.query_top_active_goals(limit=3)
    assert rows[0]["title"] == "Test Goal"
    assert calls[0][0] == "work_items"
    assert calls[0][1]["status_in"] == ("active", "in_progress")

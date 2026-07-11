"""Read-port helpers used by API / product layers."""

import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_API_KEY", "test-key")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT / "backend"))

import pytest

from app.core.runtime import read_ports
from app.core.runtime.kernel.kernel import Kernel
from app.core.runtime.reaction_registry import reset_reactions
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "ports.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    monkeypatch.setattr("app.store.database.db", db)
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

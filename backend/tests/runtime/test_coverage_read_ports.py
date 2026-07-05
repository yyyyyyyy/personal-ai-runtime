"""Coverage tests for read_ports."""
from app.core.runtime.read_ports import (
    query_conversation_messages,
    query_pending_actions,
    query_recent_inbox_emails,
    query_recent_legacy_events,
    query_top_active_goals,
)


def test_query_pending_actions_empty(isolated_kernel):
    """query_pending_actions on empty projection returns empty list."""
    result = query_pending_actions(limit=5)
    assert result == [], f"Expected empty list, got {result}"


def test_query_top_active_goals(isolated_kernel):
    """query_top_active_goals returns active goals from projection."""
    k, db = isolated_kernel
    k.emit_event("WorkItemCreated", "work_item", "goal_cov", payload={
        "title": "Coverage test goal",
    }, actor="verify")
    result = query_top_active_goals(limit=5)
    assert isinstance(result, list)
    assert len(result) > 0
    assert result[0]["title"] == "Coverage test goal"


def test_query_conversation_messages_empty(isolated_kernel):
    """query_conversation_messages on non-existent conversation returns empty."""
    result = query_conversation_messages(conversation_id="nosuchconv", limit=10)
    assert result == [], f"Expected empty list, got {result}"


def test_query_recent_inbox_emails_empty(isolated_kernel):
    """query_recent_inbox_emails on empty table returns empty."""
    result = query_recent_inbox_emails(limit=20)
    assert result == [], f"Expected empty list, got {result}"


def test_query_recent_legacy_events_empty(isolated_kernel):
    """query_recent_legacy_events on fresh DB returns empty."""
    result = query_recent_legacy_events(days=7, limit=20)
    assert result == [], f"Expected empty list, got {result}"

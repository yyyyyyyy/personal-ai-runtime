"""MessageAppended must carry role-correct actor and turn correlation_id."""

import pytest

from app.core.agents.conversation import ConversationManager


@pytest.fixture(autouse=True)
def _restore():
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    saved_k, saved_d = ki.kernel, db_mod.db
    yield
    ki.kernel, db_mod.db = saved_k, saved_d


@pytest.fixture
def kernel(isolated_kernel):
    k, _db = isolated_kernel
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db
    k.emit_event(
        "ConversationCreated",
        "conversation",
        "conv-actor",
        payload={"title": "t", "created_at": "2026-01-01T00:00:00+00:00"},
        actor="user",
    )
    return k


def test_save_message_sets_actor_by_role_and_correlation(kernel):
    mgr = ConversationManager(
        conversation_id="conv-actor",
        kernel=kernel,
        correlation_id="chat_testcorr01",
    )
    mgr.save_user_message("hi")
    mgr.save_assistant_message("hello", tool_calls=[{"id": "c1"}])
    mgr.save_tool_result('{"ok": true}', "c1")
    mgr.save_system_message("note")

    events = kernel.read_events(
        aggregate_type="conversation",
        aggregate_id="conv-actor",
        type="MessageAppended",
    )
    by_role = {e.payload["role"]: e for e in events}
    assert by_role["user"].actor == "user"
    assert by_role["assistant"].actor == "brain"
    assert by_role["tool"].actor == "brain"
    assert by_role["system"].actor == "system"
    for e in events:
        assert e.correlation_id == "chat_testcorr01"


def test_save_message_explicit_overrides(kernel):
    mgr = ConversationManager(conversation_id="conv-actor", kernel=kernel)
    mgr.save_message(
        "assistant",
        "x",
        actor="custom-actor",
        correlation_id="corr-override",
    )
    events = kernel.read_events(
        aggregate_type="conversation",
        aggregate_id="conv-actor",
        type="MessageAppended",
    )
    assert len(events) == 1
    assert events[0].actor == "custom-actor"
    assert events[0].correlation_id == "corr-override"


def test_save_user_message_idempotent_by_correlation(kernel):
    mgr = ConversationManager(
        conversation_id="conv-actor",
        kernel=kernel,
        correlation_id="chat_retry_corr",
    )
    first = mgr.save_user_message("hi again")
    second = mgr.save_user_message("hi again")
    assert first["id"] == second["id"]
    events = kernel.read_events(
        aggregate_type="conversation",
        aggregate_id="conv-actor",
        type="MessageAppended",
        correlation_id="chat_retry_corr",
    )
    user_events = [e for e in events if e.payload.get("role") == "user"]
    assert len(user_events) == 1


def test_policy_for_chat_requested_matches_tool_loop_budget():
    from app.config import settings
    from app.core.runtime.scheduled_execution import ExecutionPolicy, policy_for_event

    chat = policy_for_event("ChatRequested")
    assert chat.timeout_seconds == float(settings.total_tool_loop_timeout)
    assert chat.max_retries == 1
    assert policy_for_event("TimerFired") == ExecutionPolicy.default()


def test_message_appended_updates_conversation_ts(isolated_kernel):
    k, db = isolated_kernel
    k.emit_event(
        "ConversationCreated", "conversation", "cov_ts",
        payload={"title": "TS test"},
        actor="verify",
    )
    k.emit_event(
        "MessageAppended", "conversation", "cov_ts",
        payload={"message_id": "msg_ts", "role": "user", "content": "hello"},
        actor="verify",
    )
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT updated_at FROM conversations WHERE id = ?", ("cov_ts",)
        ).fetchone()
    assert row is not None
    assert row["updated_at"] is not None

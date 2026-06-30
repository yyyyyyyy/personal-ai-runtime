"""Coverage tests for conversation projector edges."""


def test_conversation_updated(isolated_kernel):
    """ConversationUpdated projectors update title and summary."""
    k, db = isolated_kernel
    k.emit_event("ConversationCreated", "conversation", "cov_conv", payload={
        "title": "Original Title",
    }, actor="verify")
    k.emit_event("ConversationUpdated", "conversation", "cov_conv", payload={
        "title": "Updated Title",
        "summary": "New summary",
    }, actor="verify")

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT title, summary FROM conversations WHERE id = ?", ("cov_conv",)
        ).fetchone()
        assert row is not None
        assert row["title"] == "Updated Title"
        assert row["summary"] == "New summary"


def test_conversation_deleted(isolated_kernel):
    """ConversationDeleted removes conversation and messages."""
    k, db = isolated_kernel
    k.emit_event("ConversationCreated", "conversation", "cov_del", payload={
        "title": "To Delete",
    }, actor="verify")
    k.emit_event("MessageAppended", "conversation", "cov_del", payload={
        "message_id": "msg_del",
        "role": "user",
        "content": "will be deleted",
    }, actor="verify")
    k.emit_event("ConversationDeleted", "conversation", "cov_del", payload={},
                 actor="verify")

    with db.get_db() as conn:
        c = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", ("cov_del",)
        ).fetchone()
        assert c is None
        m = conn.execute(
            "SELECT 1 FROM messages WHERE id = ?", ("msg_del",)
        ).fetchone()
        assert m is None


def test_message_appended_updates_conversation_ts(isolated_kernel):
    """MessageAppended should bump updated_at on the conversation."""
    k, db = isolated_kernel
    k.emit_event("ConversationCreated", "conversation", "cov_ts", payload={
        "title": "TS test",
    }, actor="verify")
    k.emit_event("MessageAppended", "conversation", "cov_ts", payload={
        "message_id": "msg_ts",
        "role": "user",
        "content": "hello",
    }, actor="verify")

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT updated_at FROM conversations WHERE id = ?", ("cov_ts",)
        ).fetchone()
        assert row is not None
        assert row["updated_at"] is not None

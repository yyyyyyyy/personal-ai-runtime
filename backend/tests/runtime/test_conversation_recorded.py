"""ConversationRecorded — Experience Episode in event_log."""

import pytest

from app.core.agents.handlers.chat_completed_handlers import record_conversation_turn
from app.core.runtime.kernel import Kernel
from app.core.runtime.read_ports import to_legacy_dict
from app.store.database import Database


@pytest.fixture(autouse=True)
def _restore():
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    saved_k, saved_d = ki.kernel, db_mod.db
    yield
    ki.kernel, db_mod.db = saved_k, saved_d


def test_conversation_recorded_emits_to_event_log(tmp_path):
    k = Kernel(db=Database(db_path=str(tmp_path / "conv.db")))
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db

    ev = record_conversation_turn("conv-1", "我想辞职创业", "可以先做 side project")
    assert ev.type == "ConversationRecorded"
    assert ev.seq is not None
    assert ev.correlation_id and ev.correlation_id.startswith("conv-turn-")
    assert ev.aggregate_type == "conversation"
    assert ev.aggregate_id == "conv-1"

    rows = k.read_events(type="ConversationRecorded", aggregate_id="conv-1")
    assert len(rows) == 1
    assert rows[0].payload["user_message"] == "我想辞职创业"


def test_event_formatting_maps_conversation_type(tmp_path):
    k = Kernel(db=Database(db_path=str(tmp_path / "conv2.db")))
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db

    ev = record_conversation_turn("conv-2", "hello", "hi")
    legacy = to_legacy_dict(ev)
    assert legacy["type"] == "conversation"
    assert "hello" in legacy["summary"]

def test_conversation_updated_with_summary(isolated_kernel):
    k, db = isolated_kernel
    k.emit_event(
        "ConversationCreated", "conversation", "conv_upd",
        payload={"title": "Test Conversation"},
        actor="user",
    )
    k.emit_event(
        "ConversationUpdated", "conversation", "conv_upd",
        payload={"title": "Updated Title", "summary": "A summary"},
        actor="user",
    )
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", ("conv_upd",)
        ).fetchone()
    assert row is not None
    row_dict = dict(row)
    assert row_dict["title"] == "Updated Title"
    assert row_dict["summary"] == "A summary"


def test_conversation_deleted_projector(isolated_kernel):
    k, db = isolated_kernel
    k.emit_event(
        "ConversationCreated", "conversation", "conv_del",
        payload={"title": "To Delete"},
        actor="user",
    )
    k.emit_event(
        "MessageAppended", "message", "conv_del",
        payload={"message_id": "msg_del", "role": "user", "content": "hi"},
        actor="user",
    )
    k.emit_event(
        "ConversationDeleted", "conversation", "conv_del",
        payload={}, actor="user",
    )
    with db.get_db() as conn:
        conv_row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", ("conv_del",)
        ).fetchone()
        msg_row = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ?", ("conv_del",)
        ).fetchone()
    assert conv_row is None
    assert msg_row is None

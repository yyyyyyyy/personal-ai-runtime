"""ConversationRecorded — Experience Episode in event_log."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.conversation_recorder import record_conversation_turn
from app.core.runtime.kernel import Kernel
from app.core.runtime.legacy_event_adapter import to_legacy_dict
from app.core.runtime.trajectory.engine import query_trajectory
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


def test_legacy_adapter_maps_conversation_type(tmp_path):
    k = Kernel(db=Database(db_path=str(tmp_path / "conv2.db")))
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db

    ev = record_conversation_turn("conv-2", "hello", "hi")
    legacy = to_legacy_dict(ev)
    assert legacy["type"] == "conversation"
    assert "hello" in legacy["summary"]


def test_conversation_turn_proposes_trajectory_links(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "experimental_trajectory_enabled", True)

    k = Kernel(db=Database(db_path=str(tmp_path / "conv3.db")))
    import app.core.runtime.kernel_instance as ki
    import app.store.database as db_mod

    ki.kernel = k
    db_mod.db = k._db

    ev = record_conversation_turn("conv-3", "想辞职创业", "了解")
    data = query_trajectory(k, "career-entrepreneurship-2026")
    assert data and any(lnk.get("event_seq") == ev.seq for lnk in data["links"])
    assert data["links"][0]["claim_status"] == "proposed"

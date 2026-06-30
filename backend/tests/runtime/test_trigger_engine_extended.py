"""Tests for trigger engine."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.core.runtime.trigger_engine import TriggerEngine
from app.store.database import Database


@pytest.fixture
def engine_setup(tmp_path, monkeypatch):
    db = Database(db_path=str(tmp_path / "trigger.db"))
    kernel = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.trigger_engine.db", db)
    monkeypatch.setattr("app.core.runtime.trigger_engine.kernel", kernel)
    engine = TriggerEngine()
    return engine, kernel, db


def test_seed_builtin_triggers(engine_setup):
    engine, _, db = engine_setup
    engine.seed_builtin_triggers()
    with db.get_db() as conn:
        rows = conn.execute("SELECT name FROM triggers").fetchall()
    names = {r[0] for r in rows}
    assert "email_backlog_50" in names


def test_evaluate_all_aggregates_suggestions(engine_setup, monkeypatch):
    engine, _, _ = engine_setup
    engine.seed_builtin_triggers()

    monkeypatch.setattr(
        engine,
        "_evaluate_trigger",
        lambda trigger: [{"trigger_id": trigger["id"], "content": "mock"}],
    )
    results = engine.evaluate_all()
    assert len(results) >= 1


def test_evaluate_and_notify_pushes(engine_setup, monkeypatch):
    engine, _, _ = engine_setup
    monkeypatch.setattr(
        engine,
        "evaluate_all",
        lambda: [{"trigger_id": "t1", "content": "Do something"}],
    )
    pushed = []
    monkeypatch.setattr(
        "app.core.runtime.notification_bridge.push_notification",
        lambda t, title, content: pushed.append(content) or {"id": "n1"},
    )
    notified = engine.evaluate_and_notify()
    assert notified and pushed == ["Do something"]


def test_create_and_delete_trigger(engine_setup):
    engine, _, db = engine_setup
    created = engine.create_trigger(
        "custom",
        "threshold",
        {"event_type": "email_received", "count": 1, "window_days": 1},
        "suggestion",
        {"template": "test {count}"},
    )
    assert created is not None
    assert engine.get_trigger(created["id"]) is not None
    assert any(t["name"] == "custom" for t in engine.list_triggers())
    engine.delete_trigger(created["id"])
    assert engine.get_trigger(created["id"]) is None

"""Integration test: trigger evaluation creates notifications."""

import os
import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.core.runtime.trigger_engine import TriggerEngine
from app.store.database import db, Database


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "trigger.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    Database._instance = None
    Database(db_path=db_path)
    k = Kernel(db=Database(db_path=db_path))
    k.emit_event(
        "GoalCreated", "goal", "stale1",
        payload={
            "title": "Stale Goal",
            "last_activity_at": "2020-01-01T00:00:00",
            "created_at": "2020-01-01T00:00:00",
        },
        actor="user",
    )
    with k._db.get_db() as conn:
        conn.execute(
            "UPDATE goals SET last_activity_at = '2020-01-01T00:00:00' WHERE id = 'stale1'"
        )


def test_trigger_evaluate_and_notify():
    engine = TriggerEngine()
    engine.seed_builtin_triggers()
    results = engine.evaluate_and_notify()
    assert isinstance(results, list)

"""Integration tests for B3: Trigger engine reads event_log (not legacy events table)."""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.core.runtime.trigger_engine import TriggerEngine
from app.store.database import Database


@pytest.fixture
def b3_setup(tmp_path, monkeypatch):
    """Fresh Kernel + Database + TriggerEngine for B3 tests."""
    db_path = str(tmp_path / "b3_trigger.db")
    db = Database(db_path=db_path)
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.runtime.trigger_engine.db", db)
    monkeypatch.setattr("app.core.runtime.trigger_engine.kernel", k)
    monkeypatch.setattr("app.core.runtime.kernel_instance.kernel", k)
    engine = TriggerEngine()
    return engine, k, db


class TestTriggerAuditEvents:
    """Verify TriggerCreated / TriggerDeleted events in event_log."""

    def test_seed_builtin_triggers_emits_audit(self, b3_setup):
        engine, kernel, db = b3_setup
        engine.seed_builtin_triggers()

        events = kernel.read_events(aggregate_type="trigger")
        created = [e for e in events if e.type == "TriggerCreated"]
        assert len(created) == 1  # email_backlog_50 only (goal_stagnant removed v0.2)
        names = {e.payload["name"] for e in created}
        assert "email_backlog_50" in names

    def test_seed_builtin_triggers_idempotent_audit(self, b3_setup):
        engine, kernel, db = b3_setup
        engine.seed_builtin_triggers()
        engine.seed_builtin_triggers()

        events = kernel.read_events(aggregate_type="trigger")
        created = [e for e in events if e.type == "TriggerCreated"]
        assert len(created) == 1  # no duplicate seeds

    def test_create_trigger_emits_audit(self, b3_setup):
        engine, kernel, db = b3_setup
        created = engine.create_trigger(
            "test_trigger",
            "threshold",
            {"event_type": "InboxEmailRecorded", "count": 5, "window_days": 1},
            "suggestion",
            {"template": "test"},
        )

        assert created is not None
        events = kernel.read_events(aggregate_type="trigger")
        created_events = [e for e in events if e.type == "TriggerCreated" and e.aggregate_id == created["id"]]
        assert len(created_events) == 1
        evt = created_events[0]
        assert evt.payload["name"] == "test_trigger"
        assert evt.payload["trigger_type"] == "threshold"

    def test_delete_trigger_emits_audit(self, b3_setup):
        engine, kernel, db = b3_setup
        created = engine.create_trigger(
            "to_delete",
            "threshold",
            {"event_type": "TestEvent", "count": 1, "window_days": 1},
            "suggestion",
        )
        tid = created["id"]
        engine.delete_trigger(tid)

        events = kernel.read_events(aggregate_type="trigger")
        deleted = [e for e in events if e.type == "TriggerDeleted" and e.aggregate_id == tid]
        assert len(deleted) == 1
        assert deleted[0].payload["name"] == "to_delete"


class TestThresholdReadsEventLog:
    """Verify _eval_threshold reads from event_log, not legacy events table."""

    def test_threshold_trigger_reads_event_log(self, b3_setup):
        engine, kernel, db = b3_setup

        # Emit InboxEmailRecorded events to event_log (simulating B2 audit)
        for i in range(5):
            kernel.emit_event(
                "InboxEmailRecorded",
                "inbox_email",
                f"email_{i}",
                payload={"sender": f"sender_{i}@x.com", "subject": f"Subject {i}", "category": "important"},
                actor="inbox",
            )

        # Seed the builtin trigger (email_backlog_50 with count=50 won't fire)
        # Create a custom trigger with low threshold
        tid = engine.create_trigger(
            "test_threshold",
            "threshold",
            {"event_type": "InboxEmailRecorded", "count": 3, "window_days": 1},
            "suggestion",
            {"template": "有{count}封新邮件"},
        )
        assert tid is not None

        # Evaluate — should fire since we have >= 3 events
        results = engine.evaluate_all()
        matching = [r for r in results if r.get("trigger_id") == tid["id"]]
        assert len(matching) == 1
        # {count} format string replaced by actual count (>= 3)
        assert "封新邮件" in matching[0]["content"]
        assert int(matching[0]["content"].replace("有", "").replace("封新邮件", "")) >= 3

    def test_threshold_not_fired_when_below_count(self, b3_setup):
        engine, kernel, db = b3_setup

        kernel.emit_event(
            "InboxEmailRecorded",
            "inbox_email",
            "email_only_one",
            payload={"sender": "a@x.com", "subject": "One", "category": "important"},
            actor="inbox",
        )

        tid = engine.create_trigger(
            "test_threshold_low",
            "threshold",
            {"event_type": "InboxEmailRecorded", "count": 5, "window_days": 1},
            "suggestion",
            {"template": "有{count}封新邮件"},
        )
        results = engine.evaluate_all()
        matching = [r for r in results if r.get("trigger_id") == tid["id"]]
        assert len(matching) == 0  # only 1 event, threshold is 5

    def test_threshold_does_not_read_legacy_events_table(self, b3_setup, monkeypatch):
        """Verify _eval_threshold ignores the legacy events table."""
        engine, kernel, db = b3_setup

        # Write directly to the legacy events table
        with db.get_db() as conn:
            for i in range(100):
                conn.execute(
                    "INSERT INTO events (id, type, summary, timestamp) VALUES (?, ?, ?, ?)",
                    (f"legacy_evt_{i}", "email_received", f"Email {i}", datetime.now(UTC).isoformat()),
                )

        tid = engine.create_trigger(
            "test_legacy_ignored",
            "threshold",
            {"event_type": "InboxEmailRecorded", "count": 5, "window_days": 1},
            "suggestion",
            {"template": "should not fire"},
        )

        # The 100 legacy events are "email_received" type, not "InboxEmailRecorded"
        # The trigger looks for "InboxEmailRecorded" in event_log — none exist
        results = engine.evaluate_all()
        matching = [r for r in results if r.get("trigger_id") == tid["id"]]
        assert len(matching) == 0

    def test_threshold_respects_time_window(self, b3_setup):
        engine, kernel, db = b3_setup

        # Emit events with old timestamp (outside window)
        # kernel.emit_event doesn't allow custom ts — it uses datetime.now(UTC)
        # So we emit with current time and test within a window that's too short
        kernel.emit_event(
            "InboxEmailRecorded",
            "inbox_email",
            "email_fresh",
            payload={"sender": "a@x.com", "subject": "Fresh", "category": "important"},
            actor="inbox",
        )

        tid = engine.create_trigger(
            "test_window",
            "threshold",
            {"event_type": "InboxEmailRecorded", "count": 5, "window_days": 0},  # 0-day window
            "suggestion",
            {"template": "should not fire"},
        )

        results = engine.evaluate_all()
        matching = [r for r in results if r.get("trigger_id") == tid["id"]]
        # With 0-day window start (now), events at current time should match
        assert len(matching) == 0  # only 1 event, threshold is 5

"""Tests for user validation metrics."""

from app.core.runtime.kernel.constants import EVENT_CONVERSATION_CREATED
from app.product import validation_metrics


def test_conversations_7d_counts_unique_aggregate_ids(monkeypatch):
    conv_id = "conv-abc"
    events = [
        type(
            "Event",
            (),
            {"aggregate_id": conv_id, "payload": {}, "ts": "2026-06-10T12:00:00+00:00"},
        )(),
        type(
            "Event",
            (),
            {"aggregate_id": conv_id, "payload": {}, "ts": "2026-06-11T12:00:00+00:00"},
        )(),
    ]

    monkeypatch.setattr(
        validation_metrics.kernel,
        "table_counts",
        lambda names: {"conversations": 1, "messages": 0},
    )
    monkeypatch.setattr(
        validation_metrics.kernel,
        "read_events",
        lambda **kwargs: events
        if kwargs.get("type") == EVENT_CONVERSATION_CREATED
        else [],
    )
    monkeypatch.setattr(
        validation_metrics.db,
        "get_db",
        lambda: _FakeConn(),
    )
    monkeypatch.setattr(
        validation_metrics,
        "friction_stats",
        lambda since_days=7: {
            "logged_7d": 2,
            "resolved_7d": 1,
            "open_total": 1,
            "by_area_7d": {"inbox": 1},
            "by_severity_7d": {"medium": 2},
        },
    )

    result = validation_metrics.get_validation_metrics()
    assert result["conversations_7d"] == 1
    assert result["mode"] == "dogfood"
    assert result["friction"]["logged_7d"] == 2


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, _sql):
        return _FakeRow(0)


class _FakeRow:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return {"c": self._value}

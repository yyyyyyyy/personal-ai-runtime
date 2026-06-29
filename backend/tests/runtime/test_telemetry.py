"""Telemetry unit tests."""

from datetime import UTC, datetime, timedelta

from app.core.telemetry.telemetry import telemetry


def test_get_memory_stats_compares_naive_and_aware_created_at(monkeypatch):
    recent_naive = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    recent_aware = datetime.now(UTC).isoformat()
    old_naive = (datetime.now(UTC) - timedelta(days=10)).replace(tzinfo=None).isoformat()

    monkeypatch.setattr(
        "app.core.telemetry.telemetry.kernel.query_state",
        lambda *args, **kwargs: [
            {"created_at": recent_naive, "category": "fact"},
            {"created_at": recent_aware, "category": "preference"},
            {"created_at": old_naive, "category": "fact"},
            {"category": "unknown"},
        ],
    )

    stats = telemetry.get_memory_stats()

    assert stats["total_memories"] == 4
    assert stats["recent_7d"] == 2
    assert stats["categories"]["fact"] == 2

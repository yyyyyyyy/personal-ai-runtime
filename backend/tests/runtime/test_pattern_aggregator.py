"""Tests for Pattern Aggregator — pure helpers and sliding-window detection."""

import os

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.runtime.kernel import Kernel
from app.core.runtime.kernel.event import Event
from app.core.runtime.pattern.aggregators import (
    PatternAggregator,
    _make_pattern_id,
    _time_of_day,
)
from app.store.database import Database


def test_time_of_day_buckets():
    assert _time_of_day("2026-06-10T08:30:00") == "morning"
    assert _time_of_day("2026-06-10T14:00:00") == "afternoon"
    assert _time_of_day("2026-06-10T19:00:00") == "evening"
    assert _time_of_day("2026-06-10T23:00:00") == "night"


def test_make_pattern_id_is_deterministic():
    a = _make_pattern_id("time_distribution", "coding", 14, "morning")
    b = _make_pattern_id("time_distribution", "coding", 14, "morning")
    c = _make_pattern_id("time_distribution", "coding", 14, "evening")
    assert a == b
    assert a != c
    assert a.startswith("pat_")


def test_on_event_emits_pattern_detected(tmp_path):
    import app.core.runtime.pattern.aggregators as agg_mod

    k = Kernel(db=Database(db_path=str(tmp_path / "pattern.db")))
    agg_mod.kernel = k

    agg = PatternAggregator()
    base_ts = "2026-06-10T08:00:00"

    for i in range(5):
        event = Event(
            type="ActivityNormalized",
            aggregate_type="activity",
            aggregate_id=f"act-{i}",
            payload={
                "activity_category": "coding",
                "time_of_day": "morning",
                "duration_minutes": 30,
                "topic": "python",
            },
            ts=base_ts,
            id=f"evt-{i}",
        )
        agg._on_event(event)

    detected = k.read_events(type="PatternDetected", limit=20)
    assert len(detected) >= 1
    assert any(e.payload.get("pattern_type") == "time_distribution" for e in detected)

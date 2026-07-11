"""Tests for run_memory_decay — the daily confidence decay scheduled job.

This module was excluded from coverage enforcement in pyproject.toml because
it had no dedicated tests. These tests make it testable.
"""

import pytest


class TestRunMemoryDecay:
    @pytest.fixture
    def _seed(self, isolated_kernel):
        k, _ = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m_high", payload={
            "category": "preference", "content": "high", "confidence": 0.7,
        }, actor="extractor")
        k.emit_event("MemoryDerived", "memory", "m_medium", payload={
            "category": "preference", "content": "medium", "confidence": 0.4,
        }, actor="extractor")
        k.emit_event("MemoryDerived", "memory", "m_low", payload={
            "category": "preference", "content": "low", "confidence": 0.2,
        }, actor="extractor")
        return k

    def test_no_eligible_memories_returns_zero(self, isolated_kernel):
        """Empty store → no decay events."""
        k, db = isolated_kernel
        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            count = md.run_memory_decay()
        finally:
            md.kernel = k
        assert count == 0

    def test_decays_only_at_or_below_threshold(self, isolated_kernel, _seed):
        """Confidence > 0.3 (default threshold) → skipped; ≤ 0.3 → decayed."""
        k, db = isolated_kernel

        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            count = md.run_memory_decay(threshold=0.3)
        finally:
            md.kernel = k

        # m_high=0.7 (>0.3) skipped; m_medium=0.4 (>0.3) skipped
        # m_low=0.2 (≤0.3) → decayed
        assert count == 1

        with db.get_db() as conn:
            events = conn.execute(
                "SELECT * FROM event_log WHERE type='MemoryDecayed' ORDER BY seq"
            ).fetchall()
        assert len(events) == 1
        payload = eval(events[0]["payload"]) if isinstance(events[0]["payload"], str) else events[0]["payload"]
        assert payload["confidence"] == 0.1  # max(0.1, 0.2 - 0.1)

    def test_custom_threshold(self, isolated_kernel, _seed):
        """Custom threshold: confidence ≤ 0.5 → m_medium + m_low decayed."""
        k, db = isolated_kernel

        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            count = md.run_memory_decay(threshold=0.5)
        finally:
            md.kernel = k

        # m_high=0.7 (>0.5) skipped; m_medium=0.4 (≤0.5) decayed; m_low=0.2 (≤0.5) decayed
        assert count == 2

    def test_already_decayed_is_excluded(self, isolated_kernel):
        """Memory with recent decayed_at is excluded by the SQL filter."""
        k, db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", payload={
            "category": "preference", "content": "test", "confidence": 0.25,
        }, actor="extractor")
        # Simulate a recent decay — decayed_at gets set by the projector
        k.emit_event("MemoryDecayed", "memory", "m1", payload={
            "confidence": 0.15,
        }, actor="scheduler")

        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            count = md.run_memory_decay(threshold=0.3)
        finally:
            md.kernel = k

        # m1 was just decayed → decayed_at is within 7 days → excluded by query_state
        assert count == 0

    def test_confidence_floor_respected(self, isolated_kernel):
        """Already at decay_to floor → not returned by query_state."""
        k, db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m_floor", payload={
            "category": "preference", "content": "floor", "confidence": 0.1,
        }, actor="extractor")

        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            count = md.run_memory_decay(threshold=0.3, decay_to=0.1)
        finally:
            md.kernel = k

        # confidence=0.1 = decay_to → query_state filters confidence_gt=0.1 → excluded
        assert count == 0

    def test_actor_is_scheduler(self, isolated_kernel):
        """Decay events are attributed to scheduler actor."""
        k, db = isolated_kernel
        k.emit_event("MemoryDerived", "memory", "m1", payload={
            "category": "preference", "content": "test", "confidence": 0.25,
        }, actor="extractor")

        import app.core.runtime.cron_registry as md
        md.kernel = k
        try:
            md.run_memory_decay(threshold=0.3)
        finally:
            md.kernel = k

        with db.get_db() as conn:
            event = conn.execute(
                "SELECT * FROM event_log WHERE type='MemoryDecayed' LIMIT 1"
            ).fetchone()
        assert event["actor"] == "scheduler"

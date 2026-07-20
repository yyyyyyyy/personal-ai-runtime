"""TimelineContextFragment optimization tests."""

from __future__ import annotations

from datetime import date

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.universal.timeline import (
    TimelineContextFragment,
    format_pending_action_line,
)


class TestFormatPendingActionLine:
    def test_deadline_and_work_type(self):
        line = format_pending_action_line(
            {
                "status": "pending",
                "title": "Write RFC",
                "work_type": "task",
                "deadline": "2020-01-01",
            },
            today=date(2026, 7, 17),
        )
        assert "[pending|task] Write RFC" in line
        assert "已逾期" in line


class TestTimelineCollect:
    @pytest.mark.asyncio
    async def test_pending_failure_keeps_events(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            _boom,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [
                {"summary": "WorkItem created: X", "timestamp": "2026-07-01T00:00:00", "type": "task_created"}
            ],
        )
        r = await TimelineContextFragment().collect(RuntimeContext())
        assert "## 近期事件" in r.content
        assert "WorkItem created: X" in r.content

    @pytest.mark.asyncio
    async def test_casual_filters_noisy_events(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [
                {"summary": "Conversation: hi", "timestamp": "2026-07-01", "type": "conversation"},
                {"summary": "WorkItem created: Ship", "timestamp": "2026-07-02", "type": "task_created"},
            ],
        )
        r = await TimelineContextFragment().collect(RuntimeContext())
        assert "Conversation: hi" not in r.content
        assert "WorkItem created: Ship" in r.content

    @pytest.mark.asyncio
    async def test_rich_uses_larger_pending_limit(self, monkeypatch):
        seen = {}

        def _pending(**kwargs):
            seen["pending"] = kwargs
            return []

        def _events(**kwargs):
            seen["events"] = kwargs
            return []

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            _pending,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            _events,
        )
        await TimelineContextFragment().collect(
            RuntimeContext(intent_tags=frozenset({"planning"}))
        )
        assert seen["pending"]["limit"] == 5
        assert seen["events"]["limit"] == 7

    @pytest.mark.asyncio
    async def test_pending_and_events_format(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [
                {"status": "pending", "title": "Task A"},
                {"status": "pending", "title": "Task B"},
            ],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [
                {"summary": "Goal created: Learn Rust", "timestamp": "2026-06-18T12:00:00"},
            ],
        )
        r = await TimelineContextFragment().collect(RuntimeContext())
        assert "## 待办动作" in r.content
        assert "[pending] Task A" in r.content
        assert r.content.count("- [") == 2
        assert "## 近期事件" in r.content
        assert "Goal created: Learn Rust" in r.content
        assert "(2026-06-18)" in r.content

    @pytest.mark.asyncio
    async def test_empty_actions_and_events_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_pending_actions",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_legacy_events",
            lambda **kwargs: [],
        )
        r = await TimelineContextFragment().collect(RuntimeContext())
        assert r.content == ""

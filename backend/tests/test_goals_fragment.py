"""GoalsContextFragment formatting and collect tests."""

from __future__ import annotations

from datetime import date

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.universal.goals import (
    GoalsContextFragment,
    format_goal_line,
)


class TestFormatGoalLine:
    def test_overdue_and_progress_in_rich_mode(self):
        line = format_goal_line(
            {
                "id": "g1",
                "title": "Ship v1",
                "status": "active",
                "deadline": "2020-01-01",
                "progress": 0.4,
            },
            stagnant_ids={"g1"},
            rich=True,
            today=date(2026, 7, 17),
        )
        assert "[active|停滞] Ship v1" in line
        assert "40%" in line
        assert "已逾期" in line

    def test_slim_mode_skips_progress(self):
        line = format_goal_line(
            {
                "id": "g1",
                "title": "Ship v1",
                "status": "active",
                "deadline": "2026-12-31",
                "progress": 0.4,
            },
            rich=False,
            today=date(2026, 7, 17),
        )
        assert "40%" not in line
        assert "截止 2026-12-31" in line


class TestGoalsCollect:
    @pytest.mark.asyncio
    async def test_collect_marks_stagnant_and_sources(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            lambda **kwargs: [
                {
                    "id": "g1",
                    "title": "Ship v1",
                    "status": "active",
                    "deadline": "2026-12-31T00:00:00",
                    "progress": 0.25,
                }
            ],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_stagnant_goals",
            lambda **kwargs: [{"id": "g1"}],
        )

        r = await GoalsContextFragment().collect(
            RuntimeContext(intent_tags=frozenset({"goals"}))
        )
        assert "## 当前目标" in r.content
        assert "[active|停滞] Ship v1" in r.content
        assert "25%" in r.content
        assert r.sources[0]["id"] == "g1"
        assert r.sources[0]["type"] == "goal"

    @pytest.mark.asyncio
    async def test_casual_uses_smaller_limit(self, monkeypatch):
        seen = {}

        def _goals(**kwargs):
            seen.update(kwargs)
            return []

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            _goals,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_stagnant_goals",
            lambda **kwargs: [],
        )
        await GoalsContextFragment().collect(RuntimeContext())
        assert seen["limit"] == 3

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            _boom,
        )
        r = await GoalsContextFragment().collect(RuntimeContext())
        assert r.content == ""

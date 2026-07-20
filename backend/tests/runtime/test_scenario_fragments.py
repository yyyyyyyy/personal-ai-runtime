"""Tests for scenario fragment registration and collection."""

import pytest

from app.context_runtime import RuntimeContext, fragment_registry


@pytest.fixture(autouse=True)
def _clear_registry():
    fragment_registry._fragments.clear()


class TestFragmentRegistration:

    def test_register_all_fragments(self):
        from app.fragments.register import EXPECTED_FRAGMENT_COUNT, register_all_fragments

        ids = register_all_fragments()
        assert len(ids) == EXPECTED_FRAGMENT_COUNT, (
            f"Expected {EXPECTED_FRAGMENT_COUNT} fragments, got {len(ids)}"
        )

    def test_core_goals_registered(self):
        from app.fragments.register import register_all_fragments

        register_all_fragments()
        fids = fragment_registry.list_ids()
        assert "core.goals" in fids
        assert "core.background" in fids
        assert "goals.active" not in fids

    def test_calendar_fragments_registered(self):
        from app.fragments.register import register_all_fragments

        register_all_fragments()
        fids = fragment_registry.list_ids()
        assert "calendar.today" in fids
        assert "calendar.today" in fids
        assert "calendar.upcoming" in fids


class TestFragmentCollection:

    @pytest.mark.asyncio
    async def test_core_goals_format(self, monkeypatch):
        from app.fragments.universal.goals import GoalsContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            lambda **kwargs: [
                {
                    "id": "g1",
                    "title": "Ship v1",
                    "status": "active",
                    "deadline": "2026-12-31T00:00:00",
                },
            ],
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_stagnant_goals",
            lambda **kwargs: [],
        )
        r = await GoalsContextFragment().collect(RuntimeContext())
        assert "## 当前目标" in r.content
        assert "[active] Ship v1" in r.content
        assert "截止 2026-12-31" in r.content

    @pytest.mark.asyncio
    async def test_calendar_today(self, monkeypatch):
        from app.fragments.calendar import DailyAgendaFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_calendar_today_events",
            lambda: {
                "events": [
                    {
                        "title": "Standup",
                        "start": "2026-07-17T09:30:00",
                        "location": "Room A",
                        "all_day": False,
                    }
                ]
            },
        )
        r = await DailyAgendaFragment().collect(RuntimeContext())
        assert "Calendar" in r.content
        assert "## 今日日程" in r.content
        assert "09:30  Standup @Room A" in r.content

    @pytest.mark.asyncio
    async def test_calendar_upcoming_graceful(self, monkeypatch):
        from app.fragments.calendar import UpcomingEventsFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_calendar_upcoming",
            lambda **kwargs: {
                "events": [
                    {
                        "title": "Ship review",
                        "start": "2026-07-18T14:00:00",
                        "all_day": False,
                    }
                ]
            },
        )
        r = await UpcomingEventsFragment().collect(RuntimeContext())
        assert "## 未来日程" in r.content
        assert "2026-07-18 14:00  Ship review" in r.content

    def test_core_goals_is_core_tier(self):
        from app.core.runtime.governance.fragment_selector import CORE_TIER_FRAGMENT_IDS

        assert "core.goals" in CORE_TIER_FRAGMENT_IDS

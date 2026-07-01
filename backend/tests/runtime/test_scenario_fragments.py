"""Tests for scenario fragment registration and collection."""

import os

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.context_runtime import RuntimeContext, fragment_registry


@pytest.fixture(autouse=True)
def _clear_registry():
    fragment_registry._fragments.clear()


class TestFragmentRegistration:

    def test_register_all_fragments(self):
        from app.fragments.register import register_all_fragments

        ids = register_all_fragments()
        assert len(ids) == 12, f"Expected 12 fragments, got {len(ids)}"

    def test_core_goals_registered(self):
        from app.fragments.register import register_all_fragments

        register_all_fragments()
        fids = fragment_registry.list_ids()
        assert "core.goals" in fids
        assert "core.world" in fids
        assert "goals.active" not in fids

    def test_calendar_fragments_registered(self):
        from app.fragments.register import register_all_fragments

        register_all_fragments()
        fids = fragment_registry.list_ids()
        assert "calendar.identity" in fids
        assert "calendar.today" in fids
        assert "calendar.upcoming" in fids


class TestFragmentCollection:

    @pytest.mark.asyncio
    async def test_core_goals_format(self, monkeypatch):
        from app.fragments.universal.goals import GoalsContextFragment

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_top_active_goals",
            lambda **kwargs: [
                {"title": "Ship v1", "status": "active", "deadline": "2026-12-31T00:00:00"},
            ],
        )
        r = await GoalsContextFragment().collect(RuntimeContext())
        assert "## Top Active Goals" in r.content
        assert "[active] Ship v1" in r.content

    @pytest.mark.asyncio
    async def test_calendar_identity(self):
        from app.fragments.calendar import CalendarIdentityFragment

        r = await CalendarIdentityFragment().collect(RuntimeContext())
        assert "Calendar" in r.content

    @pytest.mark.asyncio
    async def test_calendar_upcoming_graceful(self):
        from app.fragments.calendar import UpcomingEventsFragment

        r = await UpcomingEventsFragment().collect(RuntimeContext())
        assert isinstance(r.content, str)

    def test_core_goals_is_core_tier(self):
        from app.core.runtime.governance.fragment_selector import CORE_TIER_FRAGMENT_IDS

        assert "core.goals" in CORE_TIER_FRAGMENT_IDS

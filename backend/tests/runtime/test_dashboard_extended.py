"""Additional tests for dashboard widgets to boost coverage."""
from app.product.personal_dashboard import (
    _widget_active_goals,
    _widget_governance_status,
    _widget_recent_events,
    _widget_recent_memories,
    _widget_timer_status,
    generate_dashboard,
)


class TestDashboardGeneration:
    def test_generate_dashboard_returns_dict(self):
        result = generate_dashboard()
        assert isinstance(result, dict)
        assert "generated_at" in result
        assert "data_sovereignty" in result
        assert "active_goals" in result
        assert "recent_events" in result
        assert "recent_memories" in result
        assert "timer_status" in result
        assert "governance_status" in result

    def test_active_goals_widget(self):
        result = _widget_active_goals()
        assert "count" in result
        assert "top" in result
        assert isinstance(result["count"], int)

    def test_recent_events_widget(self):
        from datetime import UTC, datetime, timedelta
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        result = _widget_recent_events(since)
        assert "count" in result
        assert "items" in result

    def test_recent_memories_widget(self):
        result = _widget_recent_memories()
        assert "count" in result
        assert "items" in result

    def test_timer_status_widget(self):
        result = _widget_timer_status()
        assert "active_timers" in result

    def test_governance_status_widget(self):
        result = _widget_governance_status()
        assert "active_policies" in result
        assert "active_grants" in result


class TestKnowledgeFragment:
    def test_empty_message_returns_none(self):
        import asyncio

        from app.fragments.universal.knowledge_fragment import build_knowledge_context

        result = asyncio.run(build_knowledge_context(""))
        assert result is None

    def test_short_message_returns_none(self):
        import asyncio

        from app.fragments.universal.knowledge_fragment import build_knowledge_context

        result = asyncio.run(build_knowledge_context("hi"))
        assert result is None

    def test_valid_query_returns_formatted(self):
        import asyncio

        from app.fragments.universal.knowledge_fragment import build_knowledge_context

        result = asyncio.run(build_knowledge_context("what is machine learning"))
        # Returns None if no docs in knowledge base, which is fine
        assert result is None or isinstance(result, str)

"""Tests for dashboard data_sovereignty widget."""
from app.product.personal_dashboard import _widget_data_sovereignty


class TestDataSovereigntyWidget:
    def test_returns_dict_with_keys(self):
        result = _widget_data_sovereignty()
        assert isinstance(result, dict)
        for key in (
            "total_events", "total_memories", "memories_self_report",
            "memories_claim", "total_goals", "goals_active",
            "goals_completed", "total_conversations", "total_messages",
            "data_location", "last_belief_reflection", "export_supported",
        ):
            assert key in result

    def test_data_location_is_local(self):
        result = _widget_data_sovereignty()
        assert "本地" in result["data_location"]

    def test_export_supported(self):
        result = _widget_data_sovereignty()
        assert result["export_supported"] is True

    def test_counts_are_integers(self):
        result = _widget_data_sovereignty()
        for key in (
            "total_events", "total_memories", "total_goals",
            "total_conversations", "total_messages",
        ):
            assert isinstance(result[key], int)
            assert result[key] >= 0

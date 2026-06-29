"""Extended tests for QueryAnalyzer to cover edge intents."""
from app.core.runtime.governance.query_analyzer import QueryAnalyzer


class TestQueryAnalyzerExtended:
    def test_analyze_knowledge_intent(self):
        qa = QueryAnalyzer()
        result = qa.analyze("帮我查一下知识库里有没有关于机器学习的资料")
        assert "knowledge" in result.tags

    def test_analyze_multiple_tags(self):
        qa = QueryAnalyzer()
        result = qa.analyze("帮我规划一下本周目标，再看看邮件")
        assert len(result.tags) >= 2
        assert "planning" in result.tags or "goals" in result.tags

    def test_analyze_calendar_intent(self):
        qa = QueryAnalyzer()
        result = qa.analyze("今天有什么日程安排")
        assert "calendar" in result.tags or "planning" in result.tags

    def test_analyze_no_match(self):
        qa = QueryAnalyzer()
        result = qa.analyze("你好")
        assert isinstance(result.tags, (list, tuple, set))
        # No specific tags for generic greeting
        assert "calendar" not in result.tags

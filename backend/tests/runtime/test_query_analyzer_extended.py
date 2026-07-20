"""Extended tests for QueryAnalyzer intent tagging."""
from app.core.runtime.governance.query_analyzer import QueryAnalyzer


class TestQueryAnalyzerExtended:
    def test_analyze_planning_review_coding(self):
        qa = QueryAnalyzer()
        assert "planning" in qa.analyze("帮我规划下周的工作安排").tags
        assert "review" in qa.analyze("本周总结一下进展").tags
        assert "coding" in qa.analyze("帮我修复这个 bug").tags

    def test_analyze_knowledge_intent(self):
        qa = QueryAnalyzer()
        result = qa.analyze("帮我查一下知识库里有没有关于机器学习的资料")
        assert "knowledge" in result.tags

    def test_analyze_multiple_tags(self):
        qa = QueryAnalyzer()
        result = qa.analyze("帮我规划代码重构和本周回顾")
        assert "planning" in result.tags
        assert "coding" in result.tags
        assert "review" in result.tags

    def test_analyze_calendar_intent(self):
        qa = QueryAnalyzer()
        result = qa.analyze("今天有什么日程安排")
        assert "calendar" in result.tags or "planning" in result.tags

    def test_analyze_empty_and_greeting(self):
        qa = QueryAnalyzer()
        assert qa.analyze("").tags == set()
        assert qa.analyze("你好").tags == set()

    def test_bare_gai_is_not_coding(self):
        """Standalone 改 is too broad (改个时间 / 改提醒)."""
        qa = QueryAnalyzer()
        assert "coding" not in qa.analyze("帮我改个时间").tags
        assert "coding" not in qa.analyze("改一下提醒").tags

    def test_code_edit_phrases_are_coding(self):
        qa = QueryAnalyzer()
        assert "coding" in qa.analyze("帮我改一下代码").tags
        assert "coding" in qa.analyze("改这个函数").tags

    def test_python_optimize_is_coding(self):
        qa = QueryAnalyzer()
        assert "coding" in qa.analyze("这段 Python 怎么优化").tags

    def test_schedule_is_calendar_not_planning(self):
        """``schedule`` must not also tag planning (fragment over-selection)."""
        qa = QueryAnalyzer()
        tags = qa.analyze("please schedule a meeting tomorrow")
        assert "calendar" in tags.tags
        assert "planning" not in tags.tags

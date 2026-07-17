"""ConversationStateFragment cognitive-summary tests."""

from __future__ import annotations

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.universal.conversation_state import (
    ConversationStateFragment,
    build_conversation_state_summary,
)


class TestBuildConversationStateSummary:
    def test_extracts_topic_open_questions_and_conclusion(self):
        rows = [
            {"role": "user", "content": "项目截止日期是什么时候？"},
            {"role": "assistant", "content": "目前定在 7 月底交付。"},
            {"role": "user", "content": "那测试计划怎么安排"},
            {"role": "tool", "content": "tool-result-payload"},
            {"role": "assistant", "content": "建议本周先写集成测试。"},
        ]
        text = build_conversation_state_summary(
            rows,
            user_message="那测试计划怎么安排",
            stage="chat",
        )
        assert "## 当前会话状态" in text
        assert "当前主题: 那测试计划怎么安排" in text
        assert "待解决问题" in text
        assert "项目截止日期是什么时候" in text
        assert "最近结论/回复要点: 建议本周先写集成测试" in text
        assert "[用户]" not in text
        assert "[AI]" not in text
        assert "tool-result-payload" not in text

    def test_post_tool_includes_tool_preview(self):
        rows = [
            {"role": "user", "content": "查一下日历"},
            {"role": "tool", "content": "明天有两个会议"},
            {"role": "assistant", "content": "已查到明天两个会议。"},
        ]
        text = build_conversation_state_summary(rows, stage="post_tool")
        assert "最近工具结果: 明天有两个会议" in text


class TestConversationStateCollect:
    @pytest.mark.asyncio
    async def test_new_conversation_returns_empty(self):
        r = await ConversationStateFragment().collect(RuntimeContext(conversation_id=""))
        assert r.content == ""

    @pytest.mark.asyncio
    async def test_collect_summary_not_transcript(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_conversation_messages",
            lambda *a, **k: [
                {"role": "assistant", "content": "先做方案评审", "created_at": "2"},
                {"role": "user", "content": "下一步怎么推进？", "created_at": "1"},
            ],
        )
        r = await ConversationStateFragment().collect(
            RuntimeContext(
                conversation_id="c1",
                user_message="下一步怎么推进？",
                stage="chat",
            )
        )
        assert "当前主题" in r.content
        assert "最近结论/回复要点" in r.content
        assert "- [用户]" not in r.content

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_conversation_messages",
            _boom,
        )
        r = await ConversationStateFragment().collect(
            RuntimeContext(conversation_id="c1", user_message="hello")
        )
        assert r.content == ""

    def test_max_tokens_reduced(self):
        assert ConversationStateFragment().max_tokens == 500

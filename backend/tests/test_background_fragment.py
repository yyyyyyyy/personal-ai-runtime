"""BackgroundContextFragment optimization tests."""

from __future__ import annotations

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.universal.background import (
    BackgroundContextFragment,
    should_recall_background,
)


class TestShouldRecallBackground:
    def test_skips_greetings_and_short(self):
        assert should_recall_background("") is False
        assert should_recall_background("hi") is False
        assert should_recall_background("hello") is False
        assert should_recall_background("你好") is False
        assert should_recall_background("ok") is False

    def test_allows_substantive(self):
        assert should_recall_background("我上周说的项目截止日期是什么") is True
        assert should_recall_background("what did I decide about hiring") is True


class TestBackgroundCollect:
    @pytest.mark.asyncio
    async def test_greeting_skips_recall_keeps_world(self, monkeypatch):
        calls = {"recall": 0}

        def _recall(msg, **kwargs):
            calls["recall"] += 1
            return "## 相关记忆\n1. should-not-appear", [{"id": "m1", "type": "memory", "title": "x"}]

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            _recall,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            lambda: "## Current Life Snapshot (last 30 days)\n- Active Goals: 1",
        )

        r = await BackgroundContextFragment().collect(RuntimeContext(user_message="hello"))
        assert calls["recall"] == 0
        assert "Life Snapshot" in r.content
        assert "should-not-appear" not in r.content

    @pytest.mark.asyncio
    async def test_knowledge_tag_skips_document_recall(self, monkeypatch):
        seen = {}

        def _recall(msg, **kwargs):
            seen.update(kwargs)
            return "## 相关记忆\n1. only memory", [{"id": "m1", "type": "memory", "title": "only memory"}]

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            _recall,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            lambda: "",
        )

        r = await BackgroundContextFragment().collect(
            RuntimeContext(
                user_message="查找知识库里关于认证的文档",
                intent_tags=frozenset({"knowledge"}),
            )
        )
        assert seen.get("max_knowledge") == 0
        assert "only memory" in r.content

    @pytest.mark.asyncio
    async def test_world_failure_keeps_recall(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: ("## 相关记忆\n1. kept fact", [{"id": "m1", "type": "memory", "title": "kept fact"}]),
        )

        def _boom():
            raise RuntimeError("world down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            _boom,
        )

        r = await BackgroundContextFragment().collect(
            RuntimeContext(user_message="remind me what we planned last week")
        )
        assert "kept fact" in r.content

    @pytest.mark.asyncio
    async def test_recall_failure_keeps_world(self, monkeypatch):
        def _boom(msg, **kwargs):
            raise RuntimeError("recall down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            _boom,
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            lambda: "## Current Life Snapshot (last 30 days)\n- Active Goals: 2",
        )

        r = await BackgroundContextFragment().collect(
            RuntimeContext(user_message="remind me what we planned last week")
        )
        assert "Life Snapshot" in r.content

    @pytest.mark.asyncio
    async def test_enforces_max_tokens(self, monkeypatch):
        huge = "## 相关记忆\n" + ("fact about project planning " * 400)
        monkeypatch.setattr(
            "app.core.runtime.read_ports.retrieve_unified_with_sources",
            lambda msg, **kwargs: (huge, []),
        )
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_world_context",
            lambda: "## Current Life Snapshot (last 30 days)\n- Active Goals: 1",
        )

        frag = BackgroundContextFragment()
        frag.max_tokens = 120
        r = await frag.collect(
            RuntimeContext(user_message="what is my project planning status this month")
        )
        from app.core.agents.token_counter import count_text_tokens

        assert count_text_tokens(r.content) <= frag.max_tokens + 5
        assert "Life Snapshot" in r.content

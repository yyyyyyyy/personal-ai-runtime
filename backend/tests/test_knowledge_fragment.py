"""Knowledge fragment single-pass retrieval tests."""

from __future__ import annotations

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.universal.knowledge_context import KnowledgeContextFragment
from app.fragments.universal.knowledge_fragment import (
    build_knowledge_context,
    retrieve_knowledge_with_sources,
)


class TestRetrieveKnowledgeWithSources:
    def test_single_search_builds_content_and_sources(self, monkeypatch):
        calls = {"n": 0}

        def _search(query, **kwargs):
            calls["n"] += 1
            return [
                {
                    "id": "d1",
                    "content": "OAuth uses authorization codes for web apps.",
                    "metadata": {"source_file": "auth.md"},
                    "distance": 0.2,
                }
            ]

        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            _search,
        )
        content, sources = retrieve_knowledge_with_sources("查找知识库里的认证说明文档")
        assert calls["n"] == 1
        assert "## 相关文档" in content
        assert "[auth.md]" in content
        assert sources == [{"id": "d1", "type": "document", "title": "auth.md"}]

    def test_short_query_skips(self, monkeypatch):
        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not search")),
        )
        content, sources = retrieve_knowledge_with_sources("hi")
        assert content == ""
        assert sources == []

    def test_drops_weak_distance_hits(self, monkeypatch):
        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            lambda *a, **k: [
                {
                    "id": "weak",
                    "content": "unrelated noise blob",
                    "metadata": {"source_file": "noise.md"},
                    "distance": 0.95,
                },
                {
                    "id": "strong",
                    "content": "relevant auth material",
                    "metadata": {"source_file": "auth.md"},
                    "distance": 0.15,
                },
            ],
        )
        content, sources = retrieve_knowledge_with_sources("查找认证相关知识")
        assert "noise.md" not in content
        assert "auth.md" in content
        assert [s["id"] for s in sources] == ["strong"]

    def test_sources_match_packed_entries_under_budget(self, monkeypatch):
        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            lambda *a, **k: [
                {
                    "id": "a",
                    "content": "alpha " * 80,
                    "metadata": {"source_file": "a.md"},
                    "distance": 0.1,
                },
                {
                    "id": "b",
                    "content": "bravo " * 80,
                    "metadata": {"source_file": "b.md"},
                    "distance": 0.1,
                },
                {
                    "id": "c",
                    "content": "charlie " * 80,
                    "metadata": {"source_file": "c.md"},
                    "distance": 0.1,
                },
            ],
        )
        content, sources = retrieve_knowledge_with_sources(
            "查找知识库文档摘要",
            max_tokens=80,
        )
        assert "## 相关文档" in content
        # Only packed docs appear in sources.
        for src in sources:
            assert src["title"] in content
        assert "c.md" not in content or any(s["id"] == "c" for s in sources)
        # If c didn't fit, it must not be in sources.
        if "c.md" not in content:
            assert all(s["id"] != "c" for s in sources)


class TestKnowledgeContextFragment:
    @pytest.mark.asyncio
    async def test_collect_uses_one_search(self, monkeypatch):
        calls = {"n": 0}

        def _search(query, **kwargs):
            calls["n"] += 1
            return [
                {
                    "id": "d2",
                    "content": "Rate limits default to 100 rpm.",
                    "metadata": {"source_file": "api.md"},
                    "distance": 0.2,
                }
            ]

        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            _search,
        )
        r = await KnowledgeContextFragment().collect(
            RuntimeContext(user_message="知识库里速率限制怎么配置")
        )
        assert calls["n"] == 1
        assert "## 相关文档" in r.content
        assert r.sources[0]["id"] == "d2"

    def test_priority_raised(self):
        assert KnowledgeContextFragment().priority == 65

    def test_build_knowledge_context_compat(self, monkeypatch):
        monkeypatch.setattr(
            "app.fragments.universal.knowledge_fragment.read_ports.search_knowledge",
            lambda *a, **k: [
                {
                    "id": "d3",
                    "content": "hello world knowledge",
                    "metadata": {"source_file": "x.md"},
                    "distance": 0.2,
                }
            ],
        )
        text = build_knowledge_context("what is machine learning about")
        assert text is not None
        assert "## 相关文档" in text

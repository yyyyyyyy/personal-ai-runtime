"""Mail fragment collection, keyword extraction, and formatting tests."""

from __future__ import annotations

import pytest

from app.context_runtime import RuntimeContext
from app.fragments.mail import (
    EmailSearchFragment,
    RecentEmailsFragment,
    extract_mail_search_terms,
)


class TestExtractMailSearchTerms:
    def test_skips_intent_only_messages(self):
        assert extract_mail_search_terms("查一下邮件") == []
        assert extract_mail_search_terms("check inbox") == []

    def test_extracts_chinese_entities(self):
        terms = extract_mail_search_terms("帮我看看张三的邮件")
        assert "张三" in terms

    def test_extracts_email_and_latin(self):
        terms = extract_mail_search_terms("find email from boss@acme.com about contract")
        assert "boss@acme.com" in terms
        assert "contract" in terms

    def test_extracts_quoted_phrase(self):
        terms = extract_mail_search_terms('搜索邮件 "Q3 budget"')
        assert "Q3 budget" in terms


class TestMailFragmentCollect:
    def test_mail_fragments_hold_no_kernel(self):
        for f in (RecentEmailsFragment(), EmailSearchFragment()):
            assert not hasattr(f, "_kernel")
            assert not hasattr(f, "emit_event")
            assert not hasattr(f, "invoke_capability")

    @pytest.mark.asyncio
    async def test_recent_formats_category_status_preview(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_inbox_emails",
            lambda **kwargs: [
                {
                    "id": "m1",
                    "sender": "boss@acme.com",
                    "subject": "Q3 plan",
                    "category": "important",
                    "status": "unread",
                    "received_at": "2026-07-17T09:00:00",
                    "preview": "Please review the attached roadmap before Monday meeting.",
                }
            ],
        )
        r = await RecentEmailsFragment().collect(RuntimeContext())
        assert "Mail assistant" in r.content
        assert "[重要|未读] boss@acme.com: Q3 plan (2026-07-17)" in r.content
        assert "id: m1" in r.content
        assert "Please review the attached roadmap" in r.content
        assert r.sources[0]["id"] == "m1"
        assert r.sources[0]["type"] == "email"

    @pytest.mark.asyncio
    async def test_recent_uses_smaller_limit_when_searching(self, monkeypatch):
        seen = {}

        def _recent(**kwargs):
            seen.update(kwargs)
            return []

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_inbox_emails",
            _recent,
        )
        await RecentEmailsFragment().collect(
            RuntimeContext(user_message="帮我看看张三的邮件")
        )
        assert seen["limit"] == 8
        assert seen["order"] == "importance_desc"

    @pytest.mark.asyncio
    async def test_search_skips_without_terms(self):
        r = await EmailSearchFragment().collect(
            RuntimeContext(user_message="查一下邮件")
        )
        assert r.content == ""

    @pytest.mark.asyncio
    async def test_search_uses_extracted_terms(self, monkeypatch):
        calls: list[str] = []

        def _search(query, **kwargs):
            calls.append(query)
            return [
                {
                    "id": "m2",
                    "sender": "zhang@x.com",
                    "subject": "张三周报",
                    "category": "actionable",
                    "status": "read",
                    "received_at": "2026-07-16",
                    "preview": "本周完成两项交付",
                }
            ]

        monkeypatch.setattr(
            "app.core.runtime.read_ports.search_inbox_emails",
            _search,
        )
        r = await EmailSearchFragment().collect(
            RuntimeContext(user_message="帮我看看张三的邮件")
        )
        assert calls == ["张三"]
        assert "## 搜索结果: \"张三\"" in r.content
        assert "[待办] zhang@x.com: 张三周报" in r.content

    @pytest.mark.asyncio
    async def test_recent_exception_keeps_identity(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            "app.core.runtime.read_ports.query_recent_inbox_emails",
            _boom,
        )
        r = await RecentEmailsFragment().collect(RuntimeContext())
        assert "Mail assistant" in r.content
        assert "收件箱为空" not in r.content

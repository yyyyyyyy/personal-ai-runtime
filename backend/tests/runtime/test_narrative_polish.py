"""Narrative polish — template fallback when LLM disabled."""

import asyncio

from app.core.review_engine import ReviewEngine, _AI_SUGGESTIONS_MARKER, _PLACEHOLDER_SUGGESTIONS


def test_polish_disabled_returns_template():
    engine = ReviewEngine()
    template = "> 系统投影\n\n## 轨迹视角（连续性假说，可争议）\n- t1: test"
    out = asyncio.run(engine._finalize_review_content(template, []))
    assert out == template


def test_finalize_generates_suggestions_section_without_placeholder():
    engine = ReviewEngine()
    template = f"# DAILY 复盘\n\n{_AI_SUGGESTIONS_MARKER}\n"
    out = asyncio.run(engine._finalize_review_content(template, []))
    assert _PLACEHOLDER_SUGGESTIONS not in out
    assert _AI_SUGGESTIONS_MARKER in out

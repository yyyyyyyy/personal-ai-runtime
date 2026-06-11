"""Narrative polish — template fallback when LLM disabled."""

from app.core.review_engine import ReviewEngine


def test_polish_disabled_returns_template():
    engine = ReviewEngine()
    template = "> 系统投影\n\n## 轨迹视角（连续性假说，可争议）\n- t1: test"
    out = engine._finalize_review_content(template, [])
    assert out == template

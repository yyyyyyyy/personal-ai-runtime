"""Tests for token_counter."""

from app.core.agents.token_counter import (
    count_message_tokens,
    count_text_tokens,
    truncate_to_token_budget,
)


def test_count_text_tokens_empty():
    assert count_text_tokens("") == 0


def test_count_text_tokens_ascii():
    tokens = count_text_tokens("hello world")
    assert tokens >= 2


def test_count_message_tokens_includes_roles():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "你好"},
    ]
    tokens = count_message_tokens(messages)
    assert tokens > count_text_tokens("你好")


def test_count_message_tokens_empty_list():
    assert count_message_tokens([]) == 0


def test_count_message_tokens_none_content_fallback(monkeypatch):
    """Fallback path only sums content lengths (None → empty)."""
    monkeypatch.setattr(
        "app.core.agents.token_counter._get_encoding",
        lambda _model: None,
    )
    messages = [
        {"role": "assistant", "content": None},
        {"role": "tool", "content": "result-data"},  # 11 // 4 == 2
    ]
    assert count_message_tokens(messages) == 2


def test_count_message_tokens_tool_calls_increase_count():
    without = [{"role": "assistant", "content": "ok"}]
    with_tools = [{
        "role": "assistant",
        "content": "ok",
        "tool_calls": [{"id": "t1", "function": {"name": "get_time", "arguments": "{}"}}],
    }]
    assert count_message_tokens(with_tools) >= count_message_tokens(without)


def test_count_message_tokens_fallback_without_tiktoken(monkeypatch):
    monkeypatch.setattr(
        "app.core.agents.token_counter._get_encoding",
        lambda _model: None,
    )
    messages = [{"role": "user", "content": "abcd" * 10}]
    assert count_message_tokens(messages) == 10


def test_truncate_to_token_budget_empty_or_nonpositive():
    assert truncate_to_token_budget("", 10) == ""
    assert truncate_to_token_budget("hello", 0) == ""
    assert truncate_to_token_budget("hello", -1) == ""


def test_truncate_to_token_budget_within_limit():
    text = "short"
    assert truncate_to_token_budget(text, 100) == text


def test_truncate_to_token_budget_appends_ellipsis(monkeypatch):
    monkeypatch.setattr(
        "app.core.agents.token_counter._get_encoding",
        lambda _model: None,
    )
    # fallback: 1 token ≈ 4 chars; budget 2 tokens → ~8 chars + ellipsis
    long_text = "abcdefghijklmnop" * 4
    out = truncate_to_token_budget(long_text, 2)
    assert out.endswith("…")
    assert len(out) < len(long_text)


def test_get_encoding_swallows_network_errors(monkeypatch):
    """tiktoken download failures must not raise into chat handlers."""
    import builtins

    import app.core.agents.token_counter as tc

    class FakeTiktoken:
        @staticmethod
        def encoding_for_model(_model):
            raise OSError("DNS failed")

        @staticmethod
        def get_encoding(_name):
            raise OSError("DNS failed")

    real_import = builtins.__import__

    def import_hook(name, *args, **kwargs):
        if name == "tiktoken":
            return FakeTiktoken()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_hook)
    tc._get_encoding.cache_clear()
    assert tc._get_encoding("gpt-4") is None
    assert tc.count_text_tokens("hello") == len("hello") // 4
    tc._get_encoding.cache_clear()

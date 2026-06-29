"""Tests for token_counter."""

from app.core.agents.token_counter import count_message_tokens, count_text_tokens


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


def test_count_message_tokens_fallback_without_tiktoken(monkeypatch):
    monkeypatch.setattr(
        "app.core.agents.token_counter._get_encoding",
        lambda _model: None,
    )
    messages = [{"role": "user", "content": "abcd" * 10}]
    assert count_message_tokens(messages) == 10

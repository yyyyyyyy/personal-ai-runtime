"""Tests for brain_telemetry.record_llm_call — usage precedence."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.agents.brain_telemetry import record_llm_call


class _FakeProvider:
    name = "fake"
    model = "fake-model"
    price_per_prompt_token = 0.000001
    price_per_completion_token = 0.000002


def test_telemetry_prefers_provider_usage():
    """When usage is provided, tiktoken is NOT consulted."""
    usage = SimpleNamespace(prompt_tokens=42, completion_tokens=7)
    provider = _FakeProvider()
    with patch(
        "app.core.agents.brain_telemetry.telemetry"
    ) as mock_telemetry:
        tokens = record_llm_call(
            messages=[{"role": "user", "content": "hello"}],
            assistant_content="hi",
            llm_start=0.0,
            provider_name=provider.name,
            provider_model=provider.model,
            price_per_prompt_token=provider.price_per_prompt_token,
            price_per_completion_token=provider.price_per_completion_token,
            usage=usage,
        )
    assert tokens == 42
    record = mock_telemetry.record_llm_call.call_args.args[0]
    assert record.prompt_tokens == 42
    assert record.completion_tokens == 7


def test_telemetry_falls_back_to_tiktoken_without_usage():
    """When usage is None, tiktoken estimate is used."""
    provider = _FakeProvider()
    with patch(
        "app.core.agents.brain_telemetry.telemetry"
    ) as mock_telemetry:
        tokens = record_llm_call(
            messages=[{"role": "user", "content": "hello world"}],
            assistant_content="hi there",
            llm_start=0.0,
            provider_name=provider.name,
            provider_model=provider.model,
            price_per_prompt_token=provider.price_per_prompt_token,
            price_per_completion_token=provider.price_per_completion_token,
            usage=None,
        )
    assert tokens > 0
    record = mock_telemetry.record_llm_call.call_args.args[0]
    assert record.prompt_tokens == tokens

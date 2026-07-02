"""Tests for Brain._record_llm_telemetry usage precedence.

The telemetry helper must prefer provider-reported token usage (accurate for
CJK text) and fall back to a tiktoken estimate only when usage is absent.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.agents.brain import Brain


class _FakeProvider:
    name = "fake"
    model = "fake-model"
    price_per_prompt_token = 0.000001
    price_per_completion_token = 0.000002


def test_telemetry_prefers_provider_usage():
    """When usage is provided, tiktoken is NOT consulted."""
    usage = SimpleNamespace(prompt_tokens=42, completion_tokens=7)
    with patch("app.core.agents.brain.telemetry") as mock_telemetry:
        tokens = Brain._record_llm_telemetry(
            messages=[{"role": "user", "content": "hello"}],
            assistant_content="hi",
            used_provider=_FakeProvider(),
            llm_start=0.0,
            usage=usage,
        )
    assert tokens == 42
    record = mock_telemetry.record_llm_call.call_args.args[0]
    assert record.prompt_tokens == 42
    assert record.completion_tokens == 7


def test_telemetry_falls_back_to_tiktoken_without_usage():
    """When usage is None, tiktoken estimate is used."""
    with patch("app.core.agents.brain.telemetry") as mock_telemetry:
        tokens = Brain._record_llm_telemetry(
            messages=[{"role": "user", "content": "hello world"}],
            assistant_content="hi there",
            used_provider=_FakeProvider(),
            llm_start=0.0,
            usage=None,
        )
    assert tokens > 0
    record = mock_telemetry.record_llm_call.call_args.args[0]
    assert record.prompt_tokens == tokens

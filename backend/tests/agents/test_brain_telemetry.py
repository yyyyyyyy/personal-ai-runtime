"""Tests for brain_telemetry.record_llm_call — event-sourced telemetry writes.

Verifies that ``record_llm_call`` emits ``LLMCallRecorded`` events via the
Kernel (the single source of truth for the governed ``llm_calls`` projection),
asserting on the event payload rather than a Telemetry singleton side effect.
"""
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
    with patch("app.core.agents.brain_telemetry.kernel") as mock_kernel:
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
    # Verify emit_event was called with an LLMCallRecorded event
    mock_kernel.emit_event.assert_called_once()
    call_args = mock_kernel.emit_event.call_args
    assert call_args.args[0] == "LLMCallRecorded"
    assert call_args.kwargs["payload"]["prompt_tokens"] == 42
    assert call_args.kwargs["payload"]["completion_tokens"] == 7


def test_telemetry_falls_back_to_tiktoken_without_usage():
    """When usage is None, tiktoken estimate is used."""
    provider = _FakeProvider()
    with patch("app.core.agents.brain_telemetry.kernel") as mock_kernel:
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
    mock_kernel.emit_event.assert_called_once()
    call_args = mock_kernel.emit_event.call_args
    assert call_args.args[0] == "LLMCallRecorded"
    assert call_args.kwargs["payload"]["prompt_tokens"] == tokens

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
    """When usage is provided, tiktoken helpers are NOT consulted."""
    usage = SimpleNamespace(prompt_tokens=42, completion_tokens=7)
    provider = _FakeProvider()
    with (
        patch("app.core.agents.brain_telemetry.kernel") as mock_kernel,
        patch("app.core.agents.brain_telemetry.count_message_tokens") as mock_msg,
        patch("app.core.agents.brain_telemetry.count_text_tokens") as mock_txt,
    ):
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
    mock_msg.assert_not_called()
    mock_txt.assert_not_called()
    mock_kernel.emit_event.assert_called_once()
    call_args = mock_kernel.emit_event.call_args
    assert call_args.args[0] == "LLMCallRecorded"
    payload = call_args.kwargs["payload"]
    assert payload["prompt_tokens"] == 42
    assert payload["completion_tokens"] == 7
    expected_cost = (
        42 * provider.price_per_prompt_token
        + 7 * provider.price_per_completion_token
    )
    assert payload["cost"] == expected_cost
    assert payload["success"] is True


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


def test_record_llm_outcome_failure():
    from app.core.agents.brain_telemetry import record_llm_outcome

    with patch("app.core.agents.brain_telemetry.kernel") as mock_kernel:
        record_llm_outcome(
            provider_name="ollama",
            provider_model="qwen",
            llm_start=0.0,
            success=False,
            error_message="connection refused",
            purpose="memory_extract",
            actor="local_llm",
        )
    payload = mock_kernel.emit_event.call_args.kwargs["payload"]
    assert payload["success"] is False
    assert payload["purpose"] == "memory_extract"
    assert payload["error_message"] == "connection refused"
    assert payload["cost"] == 0.0


def test_llm_call_projector_persists_purpose(tmp_path, monkeypatch):
    from app.core.agents.brain_telemetry import record_llm_outcome
    from app.core.runtime.kernel.kernel import Kernel
    from app.store.database import Database

    db = Database(db_path=str(tmp_path / "purpose.db"))
    k = Kernel(db=db)
    monkeypatch.setattr("app.core.agents.brain_telemetry.kernel", k)

    record_llm_outcome(
        provider_name="ollama",
        provider_model="qwen",
        llm_start=0.0,
        success=True,
        prompt_tokens=3,
        completion_tokens=5,
        purpose="memory_extract",
        actor="local_llm",
    )
    rows = k.query_state("llm_calls", limit=5)
    assert len(rows) == 1
    assert rows[0]["purpose"] == "memory_extract"
    assert rows[0]["completion_tokens"] == 5

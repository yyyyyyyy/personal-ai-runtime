"""Brain Telemetry — isolated LLM call cost/latency tracking, event-sourced.

Extracted from Brain._record_llm_telemetry (v0.10.0) so the telemetry
bookkeeping is independently testable and decoupled from the Brain
orchestrator.

v0.3.0: emits LLMCallRecorded event via Kernel instead of INSERTing
directly into the llm_calls APP_STORAGE table. The projectors_telemetry
module derives the table row from the event, closing the dual-write
drift (ARCHITECTURE_SURVIVAL_REVIEW Critical #1).
"""
from __future__ import annotations

import time
from typing import Any

from app.core.agents.token_counter import count_message_tokens, count_text_tokens
from app.core.runtime.kernel_instance import kernel


def record_llm_call(
    messages: list[dict],
    assistant_content: str,
    llm_start: float,
    *,
    provider_name: str,
    provider_model: str,
    price_per_prompt_token: float,
    price_per_completion_token: float,
    usage: Any = None,
) -> int:
    """Record an LLM call to the event log. Returns the prompt token count."""
    llm_latency = (time.time() - llm_start) * 1000
    if usage is not None:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    else:
        prompt_tokens = count_message_tokens(messages, model=provider_model)
        completion_tokens = count_text_tokens(assistant_content, model=provider_model)
    estimated_cost = (
        prompt_tokens * price_per_prompt_token
        + completion_tokens * price_per_completion_token
    )
    kernel.emit_event(
        "LLMCallRecorded",
        "llm_call",
        f"llm_{time.monotonic_ns()}",
        payload={
            "provider": provider_name,
            "model": provider_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(llm_latency, 2),
            "cost": estimated_cost,
            "success": True,
        },
        actor="brain",
    )
    return prompt_tokens

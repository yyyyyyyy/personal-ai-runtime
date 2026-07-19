"""Brain Telemetry — isolated LLM call cost/latency tracking, event-sourced.

Telemetry bookkeeping is independently testable and decoupled from the Brain
orchestrator.

Emits LLMCallRecorded event via Kernel instead of INSERTing directly into the
llm_calls APP_STORAGE table. The projectors_governance module derives the table
row from the event.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.core.agents.token_counter import count_message_tokens, count_text_tokens
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)


def record_llm_outcome(
    *,
    provider_name: str,
    provider_model: str,
    llm_start: float,
    success: bool,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    price_per_prompt_token: float = 0.0,
    price_per_completion_token: float = 0.0,
    error_message: str | None = None,
    purpose: str = "chat",
    actor: str = "brain",
) -> None:
    """Record success or failure of an LLM call (chat, memory_extract, …)."""
    llm_latency = (time.time() - llm_start) * 1000
    estimated_cost = 0.0
    if success:
        estimated_cost = (
            prompt_tokens * price_per_prompt_token
            + completion_tokens * price_per_completion_token
        )
    try:
        kernel.emit_event(
            "LLMCallRecorded",
            "llm_call",
            f"llm_{time.monotonic_ns()}",
            payload={
                "provider": provider_name,
                "model": provider_model,
                "prompt_tokens": int(prompt_tokens or 0),
                "completion_tokens": int(completion_tokens or 0),
                "latency_ms": round(llm_latency, 2),
                "cost": estimated_cost,
                "success": bool(success),
                "error_message": error_message,
                "purpose": purpose,
            },
            actor=actor,
        )
    except Exception:
        logger.warning("Failed to record LLMCallRecorded (%s)", purpose, exc_info=True)


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
    purpose: str = "chat",
) -> int:
    """Record a successful LLM call. Returns the prompt token count."""
    if usage is not None:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    else:
        prompt_tokens = count_message_tokens(messages, model=provider_model)
        completion_tokens = count_text_tokens(assistant_content, model=provider_model)
    record_llm_outcome(
        provider_name=provider_name,
        provider_model=provider_model,
        llm_start=llm_start,
        success=True,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        price_per_prompt_token=price_per_prompt_token,
        price_per_completion_token=price_per_completion_token,
        purpose=purpose,
        actor="brain",
    )
    return prompt_tokens

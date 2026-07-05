"""Brain Telemetry — isolated LLM call cost/latency tracking.

Extracted from Brain._record_llm_telemetry (v0.10.0) so the telemetry
bookkeeping is independently testable and decoupled from the Brain
orchestrator.

Prefers provider-reported token usage (accurate for CJK) and falls back
to tiktoken estimates when the provider does not return usage.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.agents.token_counter import count_message_tokens, count_text_tokens
from app.core.telemetry.telemetry import LLMCallRecord, telemetry


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
    """Record an LLM call to telemetry. Returns the prompt token count.

    Args:
        messages: the full messages array sent to the LLM
        assistant_content: the textual content returned by the LLM
        llm_start: ``time.time()`` snapshot before the LLM call started
        provider_name: display name of the provider (e.g. "DeepSeek")
        provider_model: model identifier (e.g. "deepseek-chat")
        price_per_prompt_token: cost per input token in USD
        price_per_completion_token: cost per output token in USD
        usage: optional ``CompletionUsage`` object with prompt/completion
               token counts from the provider's terminal chunk
    """
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
    telemetry.record_llm_call(LLMCallRecord(
        provider=provider_name,
        model=provider_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=llm_latency,
        cost=estimated_cost,
    ))
    return prompt_tokens

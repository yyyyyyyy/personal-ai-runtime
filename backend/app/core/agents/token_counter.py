"""Token counting for LLM telemetry using tiktoken when available."""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_DEFAULT_ENCODING = "cl100k_base"


@lru_cache(maxsize=8)
def _get_encoding(model: str):
    try:
        import tiktoken
    except ImportError:
        return None

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        try:
            return tiktoken.get_encoding(_DEFAULT_ENCODING)
        except Exception as exc:
            logger.warning("tiktoken default encoding unavailable: %s", exc)
            return None
    except Exception as exc:
        # Network / cache failures must not block chat — fall back to char estimate.
        logger.warning("tiktoken encoding unavailable for %s: %s", model, exc)
        return None


def _text_content(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def count_message_tokens(messages: list[dict], *, model: str = "gpt-4") -> int:
    """Count tokens for a chat messages array."""
    encoding = _get_encoding(model)
    if encoding is None:
        return sum(len(_text_content(m.get("content"))) // 4 for m in messages)

    total = 0
    for message in messages:
        total += 4  # message framing overhead (OpenAI chat format approximation)
        for key, value in message.items():
            if key == "content":
                total += len(encoding.encode(_text_content(value)))
            elif key == "tool_calls" and value:
                total += len(encoding.encode(_text_content(value)))
            elif isinstance(value, str):
                total += len(encoding.encode(value))
    return total


def count_text_tokens(text: str, *, model: str = "gpt-4") -> int:
    """Count tokens for a single text blob."""
    encoding = _get_encoding(model)
    if encoding is None:
        return len(text) // 4
    return len(encoding.encode(text or ""))


def truncate_to_token_budget(text: str, max_tokens: int, *, model: str = "gpt-4") -> str:
    """Trim ``text`` to at most ``max_tokens`` (binary search on character length).

    Appends an ellipsis when truncation occurs. Empty input or non-positive
    budgets yield an empty string.
    """
    if not text or max_tokens <= 0:
        return ""
    if count_text_tokens(text, model=model) <= max_tokens:
        return text

    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        if not candidate:
            lo = mid + 1
            continue
        if count_text_tokens(candidate, model=model) <= max_tokens:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1

    if best and not best.endswith("…"):
        best = best.rstrip() + "…"
    return best

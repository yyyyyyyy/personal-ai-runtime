"""Local LLM — Ollama integration for high-frequency low-complexity tasks.

Used for: memory extraction, event classification, summarization.
Reduces cloud API costs and strengthens privacy-first narrative.
"""

from __future__ import annotations

import logging
import os
import time

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LocalLLM:
    """Wrapper around Ollama for local inference tasks."""

    def __init__(self):
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        from app.config import settings
        self.client = AsyncOpenAI(
            api_key="ollama",
            base_url=base_url,
            timeout=float(settings.llm_timeout_seconds),
            max_retries=3,
        )

    def _record(
        self,
        *,
        llm_start: float,
        success: bool,
        purpose: str,
        error_message: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        from app.core.agents.brain_telemetry import record_llm_outcome

        record_llm_outcome(
            provider_name="ollama",
            provider_model=self.model,
            llm_start=llm_start,
            success=success,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error_message=error_message,
            purpose=purpose,
            actor="local_llm",
        )

    async def extract_memories(self, conversation_text: str) -> list[str]:
        """Extract user preferences and facts from conversation."""
        prompt = (
            "Extract key facts and preferences about the user from this conversation. "
            "Return each fact as a separate line. Only extract clear, explicit information.\n\n"
            f"{conversation_text[:3000]}"
        )
        llm_start = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            text = response.choices[0].message.content or ""
            facts = [line.strip("- ").strip() for line in text.split("\n") if line.strip()]
            from app.core.agents.token_counter import count_text_tokens

            self._record(
                llm_start=llm_start,
                success=True,
                purpose="memory_extract",
                completion_tokens=count_text_tokens(text),
            )
            return facts
        except Exception as exc:
            logger.warning("Ollama memory extraction failed: %s", exc)
            self._record(
                llm_start=llm_start,
                success=False,
                purpose="memory_extract",
                error_message=str(exc)[:500],
            )
            return []

    async def classify_event(self, event_summary: str, categories: list[str] | None = None) -> str:
        """Classify an event into a category using local LLM."""
        cats = categories or ["work", "health", "social", "learning", "entertainment", "other"]
        prompt = f"Classify this event into one category: {', '.join(cats)}\n\nEvent: {event_summary}\n\nCategory:"
        llm_start = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.1,
            )
            result = (response.choices[0].message.content or "other").strip().lower()
            self._record(llm_start=llm_start, success=True, purpose="event_classify")
            return result if result in cats else "other"
        except Exception as exc:
            logger.warning("Ollama event classification failed: %s", exc)
            self._record(
                llm_start=llm_start,
                success=False,
                purpose="event_classify",
                error_message=str(exc)[:500],
            )
            return "other"

    async def summarize(self, text: str, max_length: int = 200) -> str:
        """Summarize text using local LLM."""
        prompt = f"Summarize the following text in under {max_length} characters:\n\n{text[:4000]}"
        llm_start = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3,
            )
            summary = (response.choices[0].message.content or "")[:max_length]
            self._record(llm_start=llm_start, success=True, purpose="summarize")
            return summary
        except Exception as exc:
            logger.warning("Ollama summarize failed: %s", exc)
            self._record(
                llm_start=llm_start,
                success=False,
                purpose="summarize",
                error_message=str(exc)[:500],
            )
            return text[:max_length]


local_llm = LocalLLM()

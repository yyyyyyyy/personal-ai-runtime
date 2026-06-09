"""Local LLM — Ollama integration for high-frequency low-complexity tasks.

Used for: memory extraction, event classification, summarization.
Reduces cloud API costs and strengthens privacy-first narrative.
"""

import os

from openai import AsyncOpenAI


class LocalLLM:
    """Wrapper around Ollama for local inference tasks."""

    def __init__(self):
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.client = AsyncOpenAI(api_key="ollama", base_url=base_url)

    async def extract_memories(self, conversation_text: str) -> list[str]:
        """Extract user preferences and facts from conversation."""
        prompt = (
            "Extract key facts and preferences about the user from this conversation. "
            "Return each fact as a separate line. Only extract clear, explicit information.\n\n"
            f"{conversation_text[:3000]}"
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            text = response.choices[0].message.content or ""
            return [line.strip("- ").strip() for line in text.split("\n") if line.strip()]
        except Exception:
            return []

    async def classify_event(self, event_summary: str, categories: list[str] | None = None) -> str:
        """Classify an event into a category using local LLM."""
        cats = categories or ["work", "health", "social", "learning", "entertainment", "other"]
        prompt = f"Classify this event into one category: {', '.join(cats)}\n\nEvent: {event_summary}\n\nCategory:"
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.1,
            )
            result = (response.choices[0].message.content or "other").strip().lower()
            return result if result in cats else "other"
        except Exception:
            return "other"

    async def summarize(self, text: str, max_length: int = 200) -> str:
        """Summarize text using local LLM."""
        prompt = f"Summarize the following text in under {max_length} characters:\n\n{text[:4000]}"
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3,
            )
            return (response.choices[0].message.content or "")[:max_length]
        except Exception:
            return text[:max_length]


local_llm = LocalLLM()

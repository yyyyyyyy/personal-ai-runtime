"""Memory Extractor — automatic fact extraction after conversation turns.

Extracts durable user facts via local LLM (Ollama) and persists them through
the Kernel as MemoryDerived events. Degrades to no-op when Ollama is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.agents.memory_engine import memory_engine

logger = logging.getLogger(__name__)

ExtractFn = Callable[[str], Awaitable[list[str]]]


class MemoryExtractor:
    """Fire-and-forget memory extraction from conversation text."""

    def __init__(self, extract_fn: ExtractFn | None = None):
        if extract_fn is not None:
            self._extract = extract_fn
        else:
            from app.core.agents.local_llm import local_llm

            self._extract = local_llm.extract_memories

    async def extract_and_store(
        self,
        conversation_text: str,
        source: str = "conversation",
    ) -> list[str]:
        """Extract facts and store each as a MemoryDerived belief. Returns stored facts."""
        if not conversation_text.strip():
            return []

        facts = await self._extract(conversation_text)
        stored: list[str] = []
        for fact in facts:
            fact = fact.strip()
            if not fact:
                continue
            memory_engine.store_memory(
                content=fact,
                category="fact",
                source=source,
                actor="extractor",
            )
            stored.append(fact)
        return stored

    def schedule(self, conversation_text: str, source: str = "conversation") -> None:
        """Schedule extraction without blocking the caller (fire-and-forget)."""

        async def _run() -> None:
            try:
                await self.extract_and_store(conversation_text, source=source)
            except Exception:
                logger.exception("Memory extraction failed")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            pass


memory_extractor = MemoryExtractor()

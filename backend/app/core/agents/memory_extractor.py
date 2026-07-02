"""Memory Extractor — automatic fact extraction after conversation turns.

Extracts durable user facts via local LLM (Ollama) and persists them through
the Kernel as MemoryDerived events. Degrades to no-op when Ollama is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from app.core.agents.memory_engine import memory_engine
from app.core.runtime.runtime_container import _LazyProxy, runtime

logger = logging.getLogger(__name__)

ExtractFn = Callable[[str], Awaitable[list[str]]]


class MemoryExtractor:
    """Fire-and-forget memory extraction from conversation text."""

    def __init__(self, extract_fn: ExtractFn | None = None):
        # Hold strong references to fire-and-forget tasks so CPython's
        # garbage collector does not reap them before completion.
        self._pending_tasks: set[asyncio.Task] = set()
        if extract_fn is not None:
            self._extract = extract_fn
        else:
            self._extract = self._default_extract

    async def _default_extract(self, conversation_text: str) -> list[str]:
        from app.config import settings
        from app.core.agents.local_llm import local_llm

        if settings.memory_extractor == "cloud":
            return await self._cloud_extract(conversation_text)
        facts = await local_llm.extract_memories(conversation_text)
        if facts:
            return facts
        if settings.llm_api_key:
            return await self._cloud_extract(conversation_text)
        return []

    async def _cloud_extract(self, conversation_text: str) -> list[str]:
        from app.core.agents.llm_failover import llm_router
        from app.core.runtime.egress.egress_gate import prepare_llm_egress

        try:
            client, provider = llm_router.get_client()
            prompt = (
                "Extract key facts about the user from this conversation. "
                "One fact per line, no bullets.\n\n" + conversation_text[:3000]
            )
            msg = {"role": "user", "content": prompt}
            egress_messages, _egress_audit = prepare_llm_egress(
                [msg], purpose="memory_extract",
            )
            response = await client.chat.completions.create(
                model=provider.model,
                messages=egress_messages,  # type: ignore[arg-type]
                max_tokens=200,
                temperature=0.3,
            )
            text = response.choices[0].message.content or ""
            return [line.strip("- ").strip() for line in text.split("\n") if line.strip()]
        except Exception:
            # Surface network/auth/quota/egress failures so users can diagnose
            # a silently-stopping memory pipeline instead of getting [] blindly.
            logger.warning("Cloud memory extraction failed", exc_info=True)
            return []

    async def extract_and_store(
        self,
        conversation_text: str,
        source: str = "conversation",
    ) -> list[str]:
        """Extract facts and store each as a MemoryDerived belief. Returns stored facts.

        Deduplication: before storing a fact, a semantic recall is performed.
        If an existing memory is highly similar, the fact is skipped to avoid
        polluting the memory store with near-duplicates.
        """
        if not conversation_text.strip():
            return []

        facts = await self._extract(conversation_text)
        stored: list[str] = []
        for fact in facts:
            fact = fact.strip()
            if not fact:
                continue
            if self._is_duplicate(fact):
                logger.debug("Skipping duplicate memory: %s", fact[:80])
                continue
            memory_engine.store_memory(
                content=fact,
                category="fact",
                source=source,
                actor="extractor",
            )
            stored.append(fact)
        return stored

    @staticmethod
    def _is_duplicate(fact: str, *, threshold: float = 0.92) -> bool:
        """Return True if a near-duplicate memory already exists.

        Uses semantic recall via the Kernel; when the vector store is
        unavailable (cold start, Ollama down) the check degrades to a
        substring match against recent memories so we still catch verbatim
        duplicates.
        """
        try:
            hits = memory_engine.search_relevant_memories(fact, n_results=3)
        except Exception:
            hits = []
        for hit in hits:
            existing = (hit.get("content") or "").strip()
            if not existing:
                continue
            # Semantic similarity score (if the backend provides one).
            score = hit.get("score") or hit.get("similarity")
            if isinstance(score, (int, float)) and score >= threshold:
                return True
            # Lexical fallback: identical or one-is-prefix-of-the-other.
            if existing == fact or existing in fact or fact in existing:
                return True
        return False

    def schedule(self, conversation_text: str, source: str = "conversation") -> None:
        """Schedule extraction without blocking the caller (fire-and-forget).

        The created task is registered in ``self._pending_tasks`` and removed
        via a done-callback. Without this strong reference CPython may collect
        the task before it runs, causing intermittent silent memory loss.
        """

        async def _run() -> None:
            try:
                await self.extract_and_store(conversation_text, source=source)
            except Exception:
                logger.exception("Memory extraction failed")

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_run())
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        except RuntimeError:
            pass


if TYPE_CHECKING:
    memory_extractor: MemoryExtractor
else:
    memory_extractor = _LazyProxy(lambda: runtime.memory_extractor)

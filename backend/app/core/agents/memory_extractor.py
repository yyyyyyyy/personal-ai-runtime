"""Memory Extractor — automatic fact extraction after conversation turns.

Extracts durable user facts via local LLM (Ollama) and persists them through
the Kernel as MemoryDerived events. Degrades to no-op when Ollama is unavailable.

Structured preference categories (preferences/values/…) belong in UserProfile;
this extractor only writes free-form MemoryDerived facts.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from app.core.agents.memory_engine import memory_engine
from app.core.runtime.runtime_container import _LazyProxy, runtime

logger = logging.getLogger(__name__)

ExtractFn = Callable[[str], Awaitable[list[str]]]

# Cap concurrent fire-and-forget extractions so chat storms cannot pile up
# Ollama/cloud jobs indefinitely.
_MAX_PENDING_TASKS = 3
# Same turn (or identical text) scheduled twice within this window is dropped.
_DEDUP_WINDOW_SEC = 120.0


class MemoryExtractor:
    """Fire-and-forget memory extraction from conversation text."""

    def __init__(self, extract_fn: ExtractFn | None = None):
        # Hold strong references to fire-and-forget tasks so CPython's
        # garbage collector does not reap them before completion.
        self._pending_tasks: set[asyncio.Task] = set()
        self._recent_keys: dict[str, float] = {}
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
        from app.core.agents.brain_telemetry import record_llm_outcome
        from app.core.agents.llm_failover import llm_router
        from app.core.runtime.egress.egress_gate import audit_llm_egress

        llm_start = time.time()
        provider_name = "cloud"
        provider_model = "unknown"
        try:
            client, provider = llm_router.get_client()
            provider_name = provider.name
            provider_model = provider.model
            prompt = (
                "Extract key facts about the user from this conversation. "
                "One fact per line, no bullets.\n\n" + conversation_text[:3000]
            )
            msg = {"role": "user", "content": prompt}
            egress_messages, _egress_audit = audit_llm_egress(
                [msg], purpose="memory_extract",
            )
            response = await client.chat.completions.create(
                model=provider.model,
                messages=egress_messages,  # type: ignore[arg-type]
                max_tokens=200,
                temperature=0.3,
            )
            text = response.choices[0].message.content or ""
            facts = [line.strip("- ").strip() for line in text.split("\n") if line.strip()]
            from app.core.agents.token_counter import count_text_tokens

            record_llm_outcome(
                provider_name=provider_name,
                provider_model=provider_model,
                llm_start=llm_start,
                success=True,
                completion_tokens=count_text_tokens(text),
                price_per_prompt_token=getattr(provider, "price_per_prompt_token", 0.0),
                price_per_completion_token=getattr(provider, "price_per_completion_token", 0.0),
                purpose="memory_extract",
                actor="extractor",
            )
            return facts
        except Exception as exc:
            logger.warning("Cloud memory extraction failed", exc_info=True)
            record_llm_outcome(
                provider_name=provider_name,
                provider_model=provider_model,
                llm_start=llm_start,
                success=False,
                error_message=str(exc)[:500],
                purpose="memory_extract",
                actor="extractor",
            )
            return []

    async def extract_and_store(
        self,
        conversation_text: str,
        source: str = "conversation",
        *,
        source_document_id: str | None = None,
        source_document_name: str | None = None,
    ) -> list[str]:
        """Extract facts and store each as a MemoryDerived belief. Returns stored facts.

        Deduplication: before storing a fact, a semantic recall is performed.
        If an existing memory is highly similar, the fact is skipped to avoid
        polluting the memory store with near-duplicates.

        When source_document_id is provided, every extracted memory is linked
        back to that document, establishing the Memory ↔ Knowledge provenance
        chain used by the "derived from" UI.
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
                source_document_id=source_document_id,
                source_document_name=source_document_name,
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
            score = hit.get("score") or hit.get("similarity")
            if isinstance(score, (int, float)) and score >= threshold:
                return True
            if existing == fact or existing in fact or fact in existing:
                return True
        return False

    def _fingerprint(self, conversation_text: str, *, dedup_key: str | None) -> str:
        if dedup_key:
            return f"key:{dedup_key}"
        digest = hashlib.sha1(conversation_text.strip().encode("utf-8")).hexdigest()[:16]
        return f"text:{digest}"

    def _prune_recent_keys(self, now: float) -> None:
        cutoff = now - _DEDUP_WINDOW_SEC
        stale = [k for k, ts in self._recent_keys.items() if ts < cutoff]
        for k in stale:
            self._recent_keys.pop(k, None)

    def schedule(
        self,
        conversation_text: str,
        source: str = "conversation",
        *,
        source_document_id: str | None = None,
        source_document_name: str | None = None,
        dedup_key: str | None = None,
    ) -> bool:
        """Schedule extraction without blocking the caller (fire-and-forget).

        Returns True when a task was scheduled, False when dropped (backlog
        full or duplicate within the dedup window).

        The created task is registered in ``self._pending_tasks`` and removed
        via a done-callback. Without this strong reference CPython may collect
        the task before it runs, causing intermittent silent memory loss.
        """
        if not conversation_text.strip():
            return False

        now = time.monotonic()
        self._prune_recent_keys(now)
        fp = self._fingerprint(conversation_text, dedup_key=dedup_key)
        if fp in self._recent_keys:
            logger.debug("Skipping duplicate memory extraction schedule: %s", fp)
            return False

        # Count only unfinished tasks toward the backlog cap.
        pending = {t for t in self._pending_tasks if not t.done()}
        self._pending_tasks = pending
        if len(pending) >= _MAX_PENDING_TASKS:
            logger.warning(
                "Memory extraction backlog full (%d); dropping schedule",
                _MAX_PENDING_TASKS,
            )
            return False

        async def _run() -> None:
            try:
                await self.extract_and_store(
                    conversation_text,
                    source=source,
                    source_document_id=source_document_id,
                    source_document_name=source_document_name,
                )
            except Exception:
                logger.exception("Memory extraction failed")

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_run())
            self._pending_tasks.add(task)
            self._recent_keys[fp] = now
            task.add_done_callback(self._pending_tasks.discard)
            return True
        except RuntimeError:
            return False


if TYPE_CHECKING:
    memory_extractor: MemoryExtractor
else:
    memory_extractor = _LazyProxy(lambda: runtime.memory_extractor)

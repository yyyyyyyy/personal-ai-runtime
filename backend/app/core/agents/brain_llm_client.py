"""Brain LLM Client — standalone LLM calling layer (v0.10.0).

Decoupled from Brain via explicit injection: the client and provider come
from ``llm_router.get_client()``, and the ``build_messages_fn`` callback
replaces the former mixin's implicit ``self._build_messages`` contract.

Heavy call logic lives in ``brain_llm_ops`` (not counted toward God Object LOC).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.core.agents.conversation import ConversationManager

# Signature of the message-building helper originally on Brain.
BuildMessagesFn = Callable[..., list[dict]]


class BrainLLMClient:
    """Stateless LLM caller: streaming, retry, one-shot, synthesis.

    ``client`` and ``provider`` are injected so multiple Brain instances
    (or tests) can use different providers without sharing mutable state.
    """

    _MAX_CONTINUE_DEPTH = 3

    def __init__(
        self,
        *,
        client: Any,
        provider: Any,
        build_messages_fn: BuildMessagesFn,
    ):
        self._client = client
        self._provider = provider
        self._build_messages_fn = build_messages_fn

    @property
    def provider(self):
        """Expose provider name for failover detection in Brain.chat_stream."""
        return self._provider

    def replace_provider(self, client: Any, provider: Any) -> None:
        """Swap client+provider after LLM failover (Brain hot path)."""
        self._client = client
        self._provider = provider

    async def continue_after_tool_result(
        self, conversation: "ConversationManager", *, depth: int = 0,
    ) -> str:
        """One-shot LLM completion after approval resolution closes the tool loop."""
        from app.core.agents import brain_llm_ops

        return await brain_llm_ops.continue_after_tool_result(
            self, conversation, depth=depth,
        )

    async def create_stream(self, messages: list[dict]):
        """Try primary LLM provider (with retries), then fallbacks."""
        from app.core.agents import brain_llm_ops

        return await brain_llm_ops.create_stream(self, messages)

    async def synthesize_from_tool_results(self, messages: list[dict]) -> str:
        """Final text-only pass when the tool loop hits its iteration cap."""
        from app.core.agents import brain_llm_ops

        return await brain_llm_ops.synthesize_from_tool_results(self, messages)

    async def complete_text_only(self, messages: list[dict], user_message: str) -> str:
        """Retry once without tools when the model returns an empty completion."""
        from app.core.agents import brain_llm_ops

        return await brain_llm_ops.complete_text_only(self, messages, user_message)

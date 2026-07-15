"""Brain — the core reasoning loop: conversation → tool calls → response.

Brain is stateless. It takes context, calls the LLM, routes tool invocations,
and returns a response. It does NOT own state — that belongs to Runtime.

Heavy streaming / LLM call logic lives in ``brain_chat_stream`` and
``brain_llm_ops`` (not counted toward God Object LOC).
"""
# mypy: disable-error-code=arg-type

from typing import AsyncIterator

from app.core.agents.brain_history_builder import build_messages
from app.core.agents.brain_llm_client import BrainLLMClient
from app.core.agents.conversation import ConversationManager
from app.core.agents.llm_failover import llm_router


class Brain:
    """Stateless reasoning engine. One instance per request.

    Uses injected ``BrainLLMClient`` for all LLM calls (streaming, one-shot,
    synthesis). Does NOT own state — that belongs to Runtime.
    """

    def __init__(self):
        client, provider = llm_router.get_client()
        self._llm = BrainLLMClient(
            client=client,
            provider=provider,
            build_messages_fn=build_messages,
        )

    async def chat_stream(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
        execution_id: str = "",
        correlation_id: str = "",
    ) -> AsyncIterator[dict]:
        """Process a user message and stream the response."""
        from app.core.agents import brain_chat_stream

        async for event in brain_chat_stream.chat_stream(
            self,
            conversation,
            user_message,
            system_prompt=system_prompt,
            execution_id=execution_id,
            correlation_id=correlation_id,
        ):
            yield event

    async def chat(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
    ) -> dict:
        """Non-streaming wrapper for chat_stream (ADR Unification: called by Handler)."""
        content = ""
        pending = False
        pending_tool_name = ""
        pending_tool_args: dict = {}
        pending_approval_id = ""
        conv_id = conversation.conversation_id

        async for event in self.chat_stream(
            conversation, user_message, system_prompt=system_prompt,
        ):
            if event.get("type") == "text_delta" and event.get("content"):
                content += event["content"]
            elif event.get("type") == "confirmation_required":
                pending = True
                pending_tool_name = event.get("tool_name", "")
                pending_tool_args = event.get("tool_args", {})
                pending_approval_id = event.get("approval_id", "")
            elif event.get("type") == "error":
                return {"status": "error", "content": event.get("content", "Unknown error")}

        return {
            "status": "ok",
            "content": content,
            "user_message": user_message,
            "conversation_id": conv_id,
            "pending": pending,
            "tool_name": pending_tool_name,
            "tool_args": pending_tool_args,
            "approval_id": pending_approval_id,
        }

    async def continue_after_tool_result(
        self, conversation: ConversationManager, *, depth: int = 0,
    ) -> str:
        """Delegate to BrainLLMClient.continue_after_tool_result."""
        return await self._llm.continue_after_tool_result(
            conversation, depth=depth,
        )

    def _build_messages(
        self,
        conversation: ConversationManager,
        user_message: str,
        *,
        system_prompt: str,
    ) -> list[dict]:
        """Delegate to brain_history_builder.build_messages."""
        return build_messages(
            conversation, user_message, system_prompt=system_prompt,
        )

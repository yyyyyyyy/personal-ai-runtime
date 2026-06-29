"""LLM completion helpers for Brain — streaming, retry, and post-tool synthesis."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.core.agents.llm_router import llm_router
from app.core.agents.tool_markup import strip_tool_markup
from app.core.runtime.egress.egress_gate import prepare_llm_egress
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.runtime_config import runtime_config
from app.core.telemetry.telemetry import LLMCallRecord, telemetry

if TYPE_CHECKING:
    from app.core.agents.conversation import ConversationManager

logger = logging.getLogger(__name__)


class BrainCompletionMixin:
    """Mixin: non-streaming LLM completion paths used after tool loops."""

    if TYPE_CHECKING:
        from app.core.agents.llm_router import LLMProvider

        _build_messages: Any
        provider: LLMProvider
        client: Any

    async def continue_after_tool_result(self, conversation: ConversationManager) -> str:
        """One-shot LLM completion after approval resolution closes the tool loop."""
        from app.chat.prompt_compiler import (
            CompileContext,
            latest_user_message_from_history,
            prompt_compiler,
        )

        history = conversation.get_history()
        latest_user = latest_user_message_from_history(history)
        system_prompt = await prompt_compiler.compile(
            CompileContext(
                conversation_id=conversation.conversation_id,
                execution_id=None,
                user_message=latest_user,
                stage="post_tool",
            ),
        )
        messages = self._build_messages(
            conversation, user_message="", system_prompt=system_prompt,
        )
        if messages and messages[-1].get("role") == "user" and not messages[-1].get("content"):
            messages.pop()

        egress_messages, _egress_audit = prepare_llm_egress(
            messages, purpose="chat_continue"
        )

        content = ""
        try:
            response = await self.client.chat.completions.create(  # type: ignore
                model=self.provider.model,
                messages=egress_messages,
                temperature=runtime_config.get_generation_params()[0],
                max_tokens=runtime_config.get_generation_params()[1],
            )
            content = response.choices[0].message.content or ""
        except Exception as e:
            logger.warning("continue_after_tool_result first attempt failed: %s", e)

        cleaned = strip_tool_markup(content)

        if not cleaned.strip():
            original_raw = content[:200] if content else "(empty)"
            logger.warning(
                "continue_after_tool_result: empty after strip, raw=%r — retrying",
                original_raw,
            )
            retry_messages = list(egress_messages)
            retry_messages.append({
                "role": "user",
                "content": "请只用文字回复，不要调用任何工具。",
            })
            try:
                response = await self.client.chat.completions.create(  # type: ignore
                    model=self.provider.model,
                    messages=retry_messages,
                    temperature=runtime_config.get_generation_params()[0],
                    max_tokens=runtime_config.get_generation_params()[1],
                )
                content = response.choices[0].message.content or ""
                cleaned = strip_tool_markup(content)
                if not cleaned.strip():
                    logger.warning(
                        "continue_after_tool_result: retry also empty, raw=%r — giving up",
                        content[:200],
                    )
                    cleaned = "操作已完成。如需继续，请告诉我下一步想做什么。"
            except Exception as e:
                logger.exception("continue_after_tool_result retry failed")
                cleaned = f"操作已完成，但无法生成后续回复：{e}"

        if cleaned.strip():
            conversation.save_assistant_message(cleaned)
        return cleaned

    async def _create_llm_stream(self, messages: list[dict]):
        """Try primary LLM provider, then fallbacks."""
        from openai import AsyncOpenAI

        from app.core.agents.llm_router import LLMProvider

        candidates: list[tuple[AsyncOpenAI, LLMProvider]] = [
            (self.client, self.provider),
            *llm_router.get_fallback_clients(),
        ]
        last_error: Exception | None = None
        llm_start = time.time()
        egress_messages, _egress_audit = prepare_llm_egress(messages, purpose="chat_stream")
        for client, provider in candidates:
            try:
                response = await client.chat.completions.create(  # type: ignore
                    model=provider.model,
                    messages=egress_messages,
                    tools=kernel.list_capability_definitions(),
                    tool_choice="auto",
                    temperature=runtime_config.get_generation_params()[0],
                    max_tokens=runtime_config.get_generation_params()[1],
                    stream=True,
                )
                return response, client, provider
            except Exception as e:
                last_error = e
                telemetry.record_llm_call(LLMCallRecord(
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=(time.time() - llm_start) * 1000,
                    success=False,
                    error_message=str(e),
                ))
        raise last_error or RuntimeError("No LLM provider available")

    async def _synthesize_from_tool_results(self, messages: list[dict]) -> str:
        """Final text-only pass when the tool loop hits its iteration cap."""
        synth_messages = list(messages)
        synth_messages.append({
            "role": "user",
            "content": (
                "已达到工具调用次数上限。请仅根据上述对话与工具返回的结果，"
                "用中文直接回答用户最初的问题，不要再调用任何工具。"
            ),
        })
        try:
            response = await self.client.chat.completions.create(  # type: ignore
                model=self.provider.model,
                messages=synth_messages,
                temperature=runtime_config.get_generation_params()[0],
                max_tokens=runtime_config.get_generation_params()[1],
            )
            return strip_tool_markup((response.choices[0].message.content or "").strip())
        except Exception:
            logger.exception("_synthesize_from_tool_results failed")
            return ""

    async def _complete_text_only(self, messages: list[dict], user_message: str) -> str:
        """Retry once without tools when the model returns an empty completion."""
        retry_messages = list(messages)
        retry_messages.append({
            "role": "user",
            "content": (
                f"{user_message}\n\n"
                "(请直接文字回复。)"
            ),
        })
        try:
            response = await self.client.chat.completions.create(  # type: ignore
                model=self.provider.model,
                messages=retry_messages,
                temperature=runtime_config.get_generation_params()[0],
                max_tokens=runtime_config.get_generation_params()[1],
            )
            return strip_tool_markup((response.choices[0].message.content or "").strip())
        except Exception:
            logger.exception("_complete_text_only retry failed")
            return "抱歉，我暂时无法生成回复，请再试一次。"

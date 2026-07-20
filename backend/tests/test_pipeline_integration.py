"""ContextPipeline wired into Brain / PromptCompiler."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestContextPipeline:
    def test_pipeline_registers_core_fragments_idempotently(self):
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        registry = FragmentRegistry()
        ContextPipeline(registry)
        ids = registry.list_ids()
        assert "core.conversation_state" in ids
        assert "core.background" in ids
        assert "core.timeline" in ids
        assert "core.goals" in ids
        assert "runtime.identity" not in ids

        before = len(ids)
        ContextPipeline(registry)
        assert len(registry.list_ids()) == before


class TestBrainWithSystemPrompt:
    def test_build_messages_requires_compiled_prompt(self):
        from app.core.agents.brain import Brain
        from app.core.agents.conversation import ConversationManager

        brain = Brain()
        conv = ConversationManager(conversation_id=f"test_{uuid.uuid4().hex[:8]}")
        with pytest.raises(RuntimeError, match="system_prompt must be compiled"):
            brain._build_messages(conv, "hello", system_prompt="")

    def test_build_messages_uses_compiled_prompt(self):
        from app.core.agents.brain import Brain
        from app.core.agents.conversation import ConversationManager

        brain = Brain()
        conv = ConversationManager(conversation_id=f"test_{uuid.uuid4().hex[:8]}")
        msg = brain._build_messages(conv, "hello", system_prompt="CUSTOM_COMPILED_PROMPT")
        assert msg[0]["role"] == "system"
        assert msg[0]["content"] == "CUSTOM_COMPILED_PROMPT"
        assert msg[-1] == {"role": "user", "content": "hello"}


class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_pipeline_planning_includes_world_fragment(self, monkeypatch):
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        monkeypatch.setattr(
            "app.core.agents.world_model.world_model.to_prompt_context",
            lambda: "## Current Life Snapshot (last 30 days)\n- Active Goals: 2",
        )
        pipeline = ContextPipeline(FragmentRegistry())
        result = await pipeline.build("帮我规划下周")
        assert "Current Life Snapshot" in result


class TestPromptCompiler:
    @pytest.mark.asyncio
    async def test_compile_includes_identity(self):
        from app.chat.prompt_compiler import CompileContext, PromptCompiler
        from app.context_runtime import FragmentRegistry
        from app.core.runtime.governance.context_pipeline import ContextPipeline

        pipeline = ContextPipeline(FragmentRegistry())
        compiler = PromptCompiler(pipeline=pipeline)
        result = await compiler.compile(
            CompileContext(
                conversation_id="conv_abc",
                execution_id="exec_1",
                user_message="你好",
                stage="chat",
            ),
        )
        assert "Personal AI Runtime" in result

    def test_latest_user_message_from_history(self):
        from app.chat.prompt_compiler import latest_user_message_from_history

        history = [
            {"role": "user", "content": "第一条"},
            {"role": "assistant", "content": "回复"},
            {"role": "tool", "content": "{}", "tool_call_id": "tc1"},
            {"role": "user", "content": "第二条"},
            {"role": "assistant", "content": "再回复"},
        ]
        assert latest_user_message_from_history(history) == "第二条"

    def test_latest_user_message_skips_empty_user_turns(self):
        from app.chat.prompt_compiler import latest_user_message_from_history

        history = [
            {"role": "user", "content": "有效消息"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": ""},
        ]
        assert latest_user_message_from_history(history) == "有效消息"

    @pytest.mark.asyncio
    async def test_post_tool_stage_uses_same_compiler(self):
        from app.chat.prompt_compiler import CompileContext, prompt_compiler

        result = await prompt_compiler.compile(
            CompileContext(
                conversation_id="conv_resume",
                execution_id=None,
                user_message="审批后继续的任务",
                stage="post_tool",
            ),
        )
        assert "Personal AI Runtime" in result


class TestContinueAfterToolResultCompile:
    @pytest.mark.asyncio
    async def test_continue_after_tool_result_uses_prompt_compiler(self, monkeypatch):
        from app.core.agents.brain import Brain
        from app.core.agents.conversation import ConversationManager

        compiled_prompt = "COMPILED_FRAGMENT_PROMPT"
        compile_mock = AsyncMock(return_value=compiled_prompt)
        monkeypatch.setattr(
            "app.chat.prompt_compiler.prompt_compiler.compile", compile_mock,
        )

        conv_id = f"test_{uuid.uuid4().hex[:8]}"
        conversation = ConversationManager(conversation_id=conv_id)
        monkeypatch.setattr(
            conversation,
            "get_history",
            lambda: [{"role": "user", "content": "用户原始问题"}],
        )
        monkeypatch.setattr(
            conversation,
            "save_assistant_message",
            lambda content, tool_calls=None: {"content": content},
        )

        brain = Brain()
        brain._llm._client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="审批后回复"))]
        brain._llm._client.chat.completions.create = AsyncMock(return_value=response)

        result = await brain.continue_after_tool_result(conversation)

        assert result == "审批后回复"
        compile_mock.assert_awaited_once()
        call_ctx = compile_mock.await_args.args[0]
        assert call_ctx.user_message == "用户原始问题"
        assert call_ctx.stage == "post_tool"
        assert call_ctx.conversation_id == conv_id

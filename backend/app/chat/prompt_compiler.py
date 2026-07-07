"""PromptCompiler — unified compile entry for Chat and Approval Resume.

Assembles Prompt Artifact (static instructions) + Context Sources (Fragment Pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.chat.prompt_artifact import PromptArtifactContext, prompt_artifact_loader
from app.config import BASE_DIR
from app.core.runtime.governance.context_pipeline import ContextPipeline, context_pipeline
from app.core.runtime.governance.context_policy import CompileStage
from app.core.runtime.kernel_instance import kernel

_ARTIFACT_CONTEXT_SEPARATOR = "\n\n---\n"


def latest_user_message_from_history(history: list[dict]) -> str:
    """Return the most recent non-empty user message from conversation history."""
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg.get("content") or ""
            if content.strip():
                return content
    return ""


@dataclass
class CompileContext:
    conversation_id: str
    execution_id: str | None
    user_message: str
    stage: CompileStage


class PromptCompiler:
    """Single compile API for ChatRequested and Approval Resume."""

    def __init__(self, pipeline: ContextPipeline | None = None):
        self._pipeline = pipeline or context_pipeline

    async def compile(
        self,
        ctx: CompileContext,
        *,
        budget: int = 32000,
    ) -> str:
        tool_defs = kernel.list_capability_definitions()
        available_tools = sorted(
            t["function"]["name"]
            for t in tool_defs
            if t.get("function", {}).get("name")
        )

        artifact = await prompt_artifact_loader.load(
            PromptArtifactContext(
                available_tools=available_tools,
                project_root=str(BASE_DIR),
                stage=ctx.stage,
            ),
        )

        context = await self._pipeline.build(
            user_message=ctx.user_message,
            conversation_id=ctx.conversation_id,
            execution_id=ctx.execution_id or "",
            budget=budget,
            stage=ctx.stage,
        )

        if not context:
            return artifact
        return f"{artifact}{_ARTIFACT_CONTEXT_SEPARATOR}{context}"


prompt_compiler = PromptCompiler()


def reset_prompt_compiler() -> None:
    """Rebuild the prompt_compiler singleton (test isolation)."""
    global prompt_compiler
    prompt_compiler = PromptCompiler()

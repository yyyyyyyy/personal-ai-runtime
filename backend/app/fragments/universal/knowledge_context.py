"""Knowledge Context Fragment — injects relevant document knowledge.

Loaded in Scenario Tier when user query matches 'knowledge' intent.
"""

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.fragments.universal.knowledge_fragment import build_knowledge_context


@dataclass
class KnowledgeContextFragment(ContextFragment):
    """Injects semantically relevant knowledge chunks from user documents."""

    id: str = field(default="scenario.knowledge", init=False)
    priority: int = field(default=50, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(
        default_factory=lambda: frozenset({"knowledge", "scenario"}), init=False
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        user_message = ctx.user_message
        if not user_message:
            return FragmentResult(content="")

        knowledge = await build_knowledge_context(user_message)
        if knowledge:
            return FragmentResult(content=knowledge)
        return FragmentResult(content="")

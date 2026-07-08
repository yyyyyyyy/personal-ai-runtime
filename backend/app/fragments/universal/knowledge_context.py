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
            # Carry document citations so the frontend can show them.
            sources: list[dict] = []
            try:
                from app.core.runtime import read_ports
                for r in read_ports.search_knowledge(user_message, n_results=TOP_K):
                    meta = r.get("metadata") or {}
                    sources.append({
                        "id": r.get("id", ""),
                        "type": "document",
                        "title": meta.get("source_file", "document"),
                    })
            except Exception:
                pass
            return FragmentResult(content=knowledge, sources=sources)
        return FragmentResult(content="")

"""Context Engine — builds rich context for LLM prompts from system state.

Context is NOT chat history. It represents the user's current most important state:
1. Active Goals (top 3)
2. Pending Actions
3. Recent Events (7 days)
4. Relevant Memories (semantic search)
5. Recent Review conclusions
"""

from dataclasses import dataclass

from app.core.agents.memory_engine import memory_engine
from app.core.agents.world_model import world_model
from app.core.runtime.kernel_instance import kernel
from app.core.runtime.legacy_event_adapter import recent_legacy_events
from app.store.database import db


@dataclass
class Context:
    """Structured context for LLM consumption."""

    active_goals: list[dict]
    pending_actions: list[dict]
    recent_events: list[dict]
    relevant_memories: str  # pre-formatted string
    recent_reviews: list[dict]
    world_snapshot: str = ""

    def to_system_prompt_appendix(self) -> str:
        """Build the context appendix for the system prompt."""
        sections = []

        if self.active_goals:
            goals_text = "\n".join(
                f"- [{g['status']}] {g['title']}"
                + (f" (deadline: {g['deadline']})" if g.get("deadline") else "")
                for g in self.active_goals[:3]
            )
            sections.append(f"## 当前活跃目标\n{goals_text}")

        if self.pending_actions:
            actions_text = "\n".join(
                f"- [{a['status']}] {a['title']}" for a in self.pending_actions[:5]
            )
            sections.append(f"## 待办行动\n{actions_text}")

        if self.recent_events:
            events_text = "\n".join(
                f"- {e['summary']} ({e['timestamp'][:10]})"
                for e in self.recent_events[:10]
            )
            sections.append(f"## 最近事件\n{events_text}")

        if self.relevant_memories:
            sections.append(self.relevant_memories)

        if self.recent_reviews:
            review = self.recent_reviews[0]
            sections.append(f"## 最近复盘\n{review['content'][:500]}")

        if self.world_snapshot:
            sections.append(self.world_snapshot)

        return "\n\n".join(sections) if sections else ""


class ContextEngine:
    """Builds context for LLM prompts from current system state."""

    def build_context(self, user_message: str) -> Context:
        """Build a full context object for the current request.

        Args:
            user_message: The user's latest message, used for memory search relevance.
        """
        active_goals = self._get_active_goals()
        pending_actions = self._get_pending_actions()
        recent_events = recent_legacy_events(kernel.read_events, days=7, limit=20)
        relevant_memories = memory_engine.retrieve_context_string(user_message)
        recent_reviews = self._get_recent_reviews()

        return Context(
            active_goals=active_goals,
            pending_actions=pending_actions,
            recent_events=recent_events,
            relevant_memories=relevant_memories,
            recent_reviews=recent_reviews,
            world_snapshot=world_model.to_prompt_context(),
        )

    def _get_active_goals(self) -> list[dict]:
        return kernel.query_state(
            "goals",
            status="active",
            limit=3,
            order="importance_urgency_desc",
        )

    def _get_pending_actions(self) -> list[dict]:
        return kernel.query_state(
            "actions",
            status="pending",
            limit=5,
            order="created_at_asc",
        )

    def _get_recent_reviews(self) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT 1"
            ).fetchall()
        return [dict(r) for r in rows]


context_engine = ContextEngine()

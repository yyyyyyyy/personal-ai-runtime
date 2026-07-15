"""Fragment registration — single entrypoint for all context fragments.

The active fragment set is: BackgroundContext, RecentEmails, DailyAgenda, and
others registered below (10 total).
"""

from __future__ import annotations

from app.context_runtime import FragmentRegistry, fragment_registry
from app.fragments.calendar import (
    DailyAgendaFragment,
    UpcomingEventsFragment,
)
from app.fragments.mail import (
    EmailSearchFragment,
    RecentEmailsFragment,
)
from app.fragments.universal.background import BackgroundContextFragment
from app.fragments.universal.conversation_state import ConversationStateFragment
from app.fragments.universal.goals import GoalsContextFragment
from app.fragments.universal.governance import GovernanceContextFragment
from app.fragments.universal.knowledge_context import KnowledgeContextFragment
from app.fragments.universal.timeline import TimelineContextFragment

_ALL_FRAGMENT_CLASSES = [
    ConversationStateFragment,
    BackgroundContextFragment,   # merged memory + world
    TimelineContextFragment,     # merged actions + events
    GoalsContextFragment,
    GovernanceContextFragment,   # runtime governance snapshot
    RecentEmailsFragment,        # merged identity + recent
    EmailSearchFragment,
    DailyAgendaFragment,         # merged identity + today
    UpcomingEventsFragment,
    KnowledgeContextFragment,
]


def register_all_fragments(registry: FragmentRegistry | None = None) -> list[str]:
    """Register all fragments into the global (or provided) registry. Idempotent."""
    reg = registry or fragment_registry
    for frag_cls in _ALL_FRAGMENT_CLASSES:
        frag = frag_cls()
        if reg.get(frag.id) is None:
            reg.register(frag)
    return reg.list_ids()

"""Fragment registration — single entrypoint for all context fragments.

v0.6.0: Actions + Events merged into TimelineFragment.
Calendar + Mail kept as separate modules but can be lazy-loaded.
Total: 13 → 10 registered (lowered by 3 via Timeline merge).
"""

from __future__ import annotations

from app.context_runtime import FragmentRegistry, fragment_registry
from app.fragments.calendar import (
    CalendarIdentityFragment,
    DailyAgendaFragment,
    UpcomingEventsFragment,
)
from app.fragments.mail import (
    EmailSearchFragment,
    MailIdentityFragment,
    RecentEmailsFragment,
)
from app.fragments.universal.conversation_state import ConversationStateFragment
from app.fragments.universal.goals import GoalsContextFragment
from app.fragments.universal.governance import GovernanceContextFragment
from app.fragments.universal.knowledge_context import KnowledgeContextFragment
from app.fragments.universal.memory import MemoryContextFragment
from app.fragments.universal.timeline import TimelineContextFragment
from app.fragments.universal.world import WorldContextFragment

_ALL_FRAGMENT_CLASSES = [
    ConversationStateFragment,
    MemoryContextFragment,
    TimelineContextFragment,    # merged actions + events
    GoalsContextFragment,
    WorldContextFragment,
    GovernanceContextFragment,  # runtime governance snapshot (FACT-36 activation)
    MailIdentityFragment,
    RecentEmailsFragment,
    EmailSearchFragment,
    CalendarIdentityFragment,
    DailyAgendaFragment,
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

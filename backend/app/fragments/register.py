"""Fragment registration — single entrypoint for all context fragments.

Active set (10):
  Core:       background, timeline, goals
  Priority:   conversation_state, governance
  Scenario:   mail (recent + search), calendar (today + upcoming), knowledge

Selection policy lives in ``fragment_selector`` (Core / Priority / Scenario /
stage sets). This module only registers instances into a FragmentRegistry.
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

# Ordered for readability only — selection order is decided by FragmentSelector.
_ALL_FRAGMENT_CLASSES = [
    # Core Tier (always in chat)
    BackgroundContextFragment,   # memory + world snapshot
    TimelineContextFragment,     # pending actions + recent events
    GoalsContextFragment,        # top active goals
    # Priority Tier (priority >= 80)
    ConversationStateFragment,   # cognitive session summary
    GovernanceContextFragment,   # pending approvals / tool status
    # Scenario Tier (intent tags)
    RecentEmailsFragment,        # mail
    EmailSearchFragment,         # mail
    DailyAgendaFragment,         # calendar
    UpcomingEventsFragment,      # calendar
    KnowledgeContextFragment,    # knowledge
]

EXPECTED_FRAGMENT_COUNT = len(_ALL_FRAGMENT_CLASSES)


def register_all_fragments(registry: FragmentRegistry | None = None) -> list[str]:
    """Register all fragments into the global (or provided) registry.

    Idempotent: existing ids are left unchanged (no overwrite).
    Returns sorted fragment ids after registration.
    """
    reg = registry or fragment_registry
    for frag_cls in _ALL_FRAGMENT_CLASSES:
        frag = frag_cls()
        if reg.get(frag.id) is None:
            reg.register(frag)
    return reg.list_ids()

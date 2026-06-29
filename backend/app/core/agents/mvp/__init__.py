"""MVP Agent definitions — Planner and Worker for validating the Multi-Agent Runtime.

Projector First: Agent state lives in projection tables, not in-memory reducers.
The Event Log IS the bus — SubscriptionRules describe which events each Agent
selects from the global append-only event_log.

Event routing is handled by HandlerRegistry (handler_registry.py), not by
each Agent.  Handlers are registered globally via @subscribe("EventType")
and the Runtime dispatches events to the correct handler automatically.
This means the same Handler can be assembled onto different RuntimeProcess
configurations without code duplication.
"""

from app.core.runtime.agent_definition import AgentDefinition, SubscriptionRule

# Import handlers to register @subscribe decorators
from . import (
    bypass_handlers,  # noqa: E402, F401
    chat_handler,  # noqa: E402, F401
    timer_trigger_handler,  # noqa: E402, F401
)

# ── Planner Agent ───────────────────────────────────────────────────────────

PLANNER_DEFINITION = AgentDefinition(
    agent_id="planner_v1",
    tools=["get_current_time", "web_search", "list_directory", "read_file"],
    subscriptions=[
        SubscriptionRule(event_type="TaskCreated"),
        SubscriptionRule(event_type="TaskCompleted"),
    ],
)

# ── Worker Agent ────────────────────────────────────────────────────────────

WORKER_DEFINITION = AgentDefinition(
    agent_id="worker_v1",
    tools=["web_search", "list_directory", "read_file"],
    subscriptions=[
        SubscriptionRule(event_type="TaskPlanned"),
    ],
)

# ── Chat Agent (ADR Unification) ───────────────────────────────────────────

CHAT_DEFINITION = AgentDefinition(
    agent_id="chat_v1",
    tools=["*"],
    subscriptions=[
        SubscriptionRule(event_type="ChatRequested"),
        SubscriptionRule(event_type="ApproveRequested"),
        SubscriptionRule(event_type="ExecuteRequested"),
        SubscriptionRule(event_type="BackgroundTaskRequested"),
        SubscriptionRule(event_type="InboxPollRequested"),
        SubscriptionRule(event_type="TimerFired"),
    ],
)

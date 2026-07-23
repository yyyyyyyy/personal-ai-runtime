"""Runtime Ports ABI — Fragment / API / Product-facing port surface.

Package path remains ``app.core.runtime.read_ports`` for stability; the role is
broader than projection reads. Callers use these ports instead of opening DB
sessions, importing ORM models, or reaching deep Runtime modules
(``task_engine``, ``reaction_registry``, bridges, scheduler internals).

    Caller → Port → Kernel / Runtime internals

Split by domain under this package. Includes:

- **Reads** — governed projection queries (``query_*`` / ``count_*``)
- **Commands** — Work mutations, trigger registration (lazy wrappers)
- **Bridges** — SSE queue register/unregister, notification push

Import via ``from app.core.runtime.read_ports import …`` or
``from app.core.runtime import read_ports``.
"""

from app.core.runtime.notification_bridge import NotificationPayload
from app.core.runtime.read_ports.approvals import (
    query_approval,
    query_approvals,
    query_pending_approval_count,
    query_pending_approvals,
)
from app.core.runtime.read_ports.calendar_mcp import (
    get_mcp_server_status,
    get_mcp_server_tools,
    query_calendar_today_events,
    query_calendar_upcoming,
    query_world_context,
    test_mcp_connection,
)
from app.core.runtime.read_ports.conversation import (
    get_conversation_sources,
    query_conversation,
    query_conversation_messages,
    query_conversations,
    query_message,
)
from app.core.runtime.read_ports.events import (
    goal_events,
    query_recent_legacy_events,
    recent_events,
    to_legacy_dict,
)
from app.core.runtime.read_ports.inbox import (
    count_pending_inbox_emails,
    query_inbox_email,
    query_inbox_emails,
    query_pending_inbox_emails,
    query_recent_inbox_emails,
    search_inbox_emails,
)
from app.core.runtime.read_ports.knowledge import (
    recall_unified,
    retrieve_unified_with_sources,
    search_knowledge,
)
from app.core.runtime.read_ports.memory import (
    build_memory_graph_edges,
    count_memories,
    query_memories,
    query_memory,
    retrieve_memory_context,
    retrieve_memory_with_sources,
    summarize_memory_stats,
)
from app.core.runtime.read_ports.notifications import (
    create_notification,
    find_notification,
    push_notification,
    query_notification,
    query_notifications,
    query_unread_notification_count,
    register_sse_queue,
    unregister_sse_queue,
)
from app.core.runtime.read_ports.profile import (
    query_user_profile,
    query_user_profile_category,
)
from app.core.runtime.read_ports.telemetry import (
    query_llm_calls,
    query_recent_tool_names,
    query_tool_calls,
    summarize_call_failure_rates,
    summarize_llm_calls,
    summarize_llm_calls_by_model,
    summarize_tool_calls,
)
from app.core.runtime.read_ports.timers import (
    cancel_background_task,
    count_active_policies,
    count_active_timers,
    count_state_selectors,
    list_trigger_reactions,
    query_active_policies,
    query_active_timers,
    query_background_task,
    query_background_tasks,
    query_due_timers,
    query_timer,
    register_trigger_reaction,
    unregister_trigger_reaction,
)
from app.core.runtime.read_ports.work import (
    bump_parent_activity,
    count_active_goals,
    count_completed_goals,
    count_goals,
    create_work_item,
    delete_work_item,
    get_sub_work_items,
    get_work_item,
    get_work_item_tree,
    list_work_items,
    query_active_goals,
    query_completed_goals,
    query_goal,
    query_goal_actions,
    query_goals,
    query_goals_with_deadline,
    query_pending_actions,
    query_pending_work_items,
    query_stagnant_goal_count,
    query_stagnant_goals,
    query_top_active_goals,
    query_work_item,
    query_work_items,
    query_work_items_by_parent_goal,
    update_work_item_fields,
    update_work_item_status,
)

__all__ = [
    "count_active_goals",
    "count_completed_goals",
    "count_goals",
    "count_memories",
    "summarize_memory_stats",
    "query_pending_actions",
    "query_top_active_goals",
    "query_stagnant_goals",
    "query_stagnant_goal_count",
    "query_work_item",
    "query_work_items",
    "query_goals",
    "query_goal",
    "query_goal_actions",
    "query_work_items_by_parent_goal",
    "query_active_goals",
    "query_completed_goals",
    "query_goals_with_deadline",
    "query_pending_work_items",
    "create_work_item",
    "update_work_item_fields",
    "update_work_item_status",
    "delete_work_item",
    "get_work_item",
    "get_sub_work_items",
    "get_work_item_tree",
    "list_work_items",
    "bump_parent_activity",
    "retrieve_memory_context",
    "retrieve_memory_with_sources",
    "query_memory",
    "query_memories",
    "recall_unified",
    "retrieve_unified_with_sources",
    "search_knowledge",
    "query_conversation_messages",
    "query_conversation",
    "query_conversations",
    "query_message",
    "get_conversation_sources",
    "query_recent_inbox_emails",
    "search_inbox_emails",
    "query_pending_inbox_emails",
    "count_pending_inbox_emails",
    "query_inbox_email",
    "query_inbox_emails",
    "query_pending_approval_count",
    "query_pending_approvals",
    "query_approval",
    "query_approvals",
    "query_notification",
    "query_notifications",
    "query_unread_notification_count",
    "NotificationPayload",
    "create_notification",
    "find_notification",
    "push_notification",
    "register_sse_queue",
    "unregister_sse_queue",
    "query_llm_calls",
    "query_tool_calls",
    "query_recent_tool_names",
    "summarize_llm_calls",
    "summarize_llm_calls_by_model",
    "summarize_tool_calls",
    "summarize_call_failure_rates",
    "query_world_context",
    "query_calendar_upcoming",
    "query_calendar_today_events",
    "get_mcp_server_status",
    "get_mcp_server_tools",
    "test_mcp_connection",
    "query_background_task",
    "query_background_tasks",
    "cancel_background_task",
    "query_active_timers",
    "count_active_timers",
    "query_timer",
    "query_due_timers",
    "query_active_policies",
    "count_active_policies",
    "register_trigger_reaction",
    "list_trigger_reactions",
    "unregister_trigger_reaction",
    "count_state_selectors",
    "query_user_profile_category",
    "query_user_profile",
    "to_legacy_dict",
    "goal_events",
    "recent_events",
    "query_recent_legacy_events",
    "build_memory_graph_edges",
]

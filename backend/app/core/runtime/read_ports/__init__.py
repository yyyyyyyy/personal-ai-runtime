"""Runtime Read Ports — Fragment-facing read abstractions.

Fragments must use these ports instead of opening DB sessions,
importing ORM models, or calling Kernel / storage directly.

    Fragment → Read Port → Kernel → Projection / Query Model

This package is split by domain; public names are re-exported here
(``from app.core.runtime.read_ports import …``).
"""

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
)
from app.core.runtime.read_ports.notifications import (
    query_notification,
    query_notifications,
)
from app.core.runtime.read_ports.profile import (
    query_user_profile,
    query_user_profile_category,
)
from app.core.runtime.read_ports.telemetry import (
    query_llm_calls,
    query_recent_tool_names,
    query_tool_calls,
)
from app.core.runtime.read_ports.timers import (
    query_active_policies,
    query_active_timers,
    query_background_task,
    query_background_tasks,
    query_due_timers,
    query_timer,
)
from app.core.runtime.read_ports.work import (
    count_active_goals,
    count_completed_goals,
    count_goals,
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
)

__all__ = [
    "count_active_goals",
    "count_completed_goals",
    "count_goals",
    "count_memories",
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
    "query_recent_inbox_emails",
    "search_inbox_emails",
    "query_pending_inbox_emails",
    "query_inbox_email",
    "query_inbox_emails",
    "query_pending_approval_count",
    "query_pending_approvals",
    "query_approval",
    "query_approvals",
    "query_notification",
    "query_notifications",
    "query_llm_calls",
    "query_tool_calls",
    "query_recent_tool_names",
    "query_world_context",
    "query_calendar_upcoming",
    "query_calendar_today_events",
    "get_mcp_server_status",
    "get_mcp_server_tools",
    "test_mcp_connection",
    "query_background_task",
    "query_background_tasks",
    "query_active_timers",
    "query_timer",
    "query_due_timers",
    "query_active_policies",
    "query_user_profile_category",
    "query_user_profile",
    "to_legacy_dict",
    "goal_events",
    "recent_events",
    "query_recent_legacy_events",
    "build_memory_graph_edges",
]

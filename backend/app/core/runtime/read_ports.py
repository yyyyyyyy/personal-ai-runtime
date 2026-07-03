"""Runtime Read Ports — Fragment-facing read abstractions.

Fragments must use these ports instead of opening DB sessions,
importing ORM models, or calling Kernel / storage directly.

    Fragment → Read Port → Kernel → Projection / Query Model
"""

from __future__ import annotations

import json
from datetime import date as date_type
from typing import Any

from app.core.runtime.kernel_instance import kernel
from app.core.runtime.event_formatting import recent_events


def query_pending_actions(*, limit: int = 5) -> list[dict[str, Any]]:
    """Query pending work items (v0.5.0: replaces actions table)."""
    return kernel.query_state(
        "work_items",
        status="pending",
        limit=limit,
        order="created_at_asc",
    )


def query_top_active_goals(*, limit: int = 5) -> list[dict[str, Any]]:
    return kernel.query_state(
        "goals",
        status_in=("active", "in_progress"),
        limit=limit,
        order="importance_urgency_desc",
    )


def query_conversation_messages(
    conversation_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return kernel.query_state(
        "messages",
        conversation_id=conversation_id,
        limit=limit,
        order="created_at_desc",
    )


def query_recent_inbox_emails(*, limit: int = 20) -> list[dict[str, Any]]:
    return kernel.query_state(
        "inbox_emails",
        status_not="archived",
        limit=limit,
        order="date_desc",
    )


def search_inbox_emails(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    return kernel.query_state(
        "inbox_emails",
        search=query,
        limit=limit,
        order="date_desc",
    )


def query_recent_legacy_events(*, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    return recent_events(
        kernel.read_events,
        days=days,
        limit=limit,
    )


def retrieve_memory_context(query: str, *, max_memories: int = 3) -> str:
    from app.core.agents.memory_engine import memory_engine

    return memory_engine.retrieve_context_string(query, max_memories=max_memories)


def retrieve_memory_with_sources(query: str, *, max_memories: int = 3) -> tuple[str, list[dict]]:
    """Retrieve memory context and return (context_str, sources)."""
    from app.core.agents.memory_engine import memory_engine

    hits = memory_engine.search_relevant_memories(query, n_results=max_memories)
    enriched = memory_engine._enrich_recall_hits(hits)
    context_str = memory_engine.format_memory_context(enriched)
    sources = [
        {"id": mem["id"], "type": "memory", "title": mem.get("content", "")[:80]}
        for mem in enriched
        if mem.get("id")
    ]
    return context_str, sources


def search_knowledge(query: str, *, n_results: int = 3) -> list[dict[str, Any]]:
    return kernel.recall_knowledge(query, k=n_results)


def query_world_context() -> str:
    from app.core.agents.world_model import world_model

    return world_model.to_prompt_context()


def query_calendar_upcoming(*, days: int = 7) -> dict[str, Any]:
    from app.core.harness.builtin_tools.calendar import calendar_server

    raw = calendar_server.get_upcoming(days=days)
    return json.loads(raw)


def query_calendar_today_events() -> dict[str, Any]:
    from app.core.harness.builtin_tools.calendar import calendar_server

    today = date_type.today().isoformat()
    raw = calendar_server.list_events(date=today, days=1)
    return json.loads(raw)


# ── MCP Connector Read Ports ──────────────────────────────────────────────

def get_mcp_server_status(server_name: str) -> dict[str, Any]:
    """Get status info for an external MCP server via MCPMesh."""
    from app.core.harness.mcp_mesh import mcp_mesh

    conn = mcp_mesh._connections.get(server_name)
    if conn and conn.session is not None:
        return {"connected": True, "tool_count": len(conn.tools)}
    return {"connected": False, "tool_count": 0}


def get_mcp_server_tools(server_name: str) -> list[dict[str, str]]:
    """Get list of tools from an external MCP server via MCPMesh."""
    from app.core.harness.mcp_mesh import mcp_mesh

    conn = mcp_mesh._connections.get(server_name)
    if not conn or not conn.tools:
        return []
    return [
        {"name": t.name, "description": (getattr(t, "description", "") or "")[:100]}
        for t in conn.tools
    ]


def test_mcp_connection(server_name: str) -> dict[str, Any]:
    """Test connection to an external MCP server."""
    status = get_mcp_server_status(server_name)
    if status.get("connected"):
        return {"status": "ok", "message": f"连接器 {server_name} 运行正常", "tool_count": status.get("tool_count", 0)}
    return {"status": "error", "message": f"连接器 {server_name} 未连接"}


# ── Governance read ports (FACT-36 activation) ────────────────────────────


def query_pending_approval_count() -> int:
    """Count approvals currently waiting for user decision."""
    try:
        rows = kernel.query_state("approvals", status="pending", limit=50)
        return len(rows)
    except Exception:
        return 0


def query_recent_tool_names(*, limit: int = 3) -> list[str]:
    """Return the names of the most recently invoked capabilities."""
    try:
        events = kernel.read_events(type="CapabilityInvoked", limit=limit, order="desc")
        names: list[str] = []
        for evt in events:
            name = evt.payload.get("name", "")
            if name and name not in names:
                names.append(name)
        return names[:limit]
    except Exception:
        return []


def query_stagnant_goal_count(*, days: int = 3) -> int:
    """Count active goals with no recent activity."""
    try:
        rows = kernel.query_state(
            "goals", status="active",
            last_activity_older_than_days=days, limit=10,
        )
        return len(rows)
    except Exception:
        return 0

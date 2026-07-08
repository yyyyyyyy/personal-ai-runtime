"""Runtime Read Ports — Fragment-facing read abstractions.

Fragments must use these ports instead of opening DB sessions,
importing ORM models, or calling Kernel / storage directly.

    Fragment → Read Port → Kernel → Projection / Query Model
"""

from __future__ import annotations

import json
import logging
from datetime import date as date_type
from typing import Any

from app.core.runtime.event_formatting import recent_events
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)


def query_pending_actions(*, limit: int = 5) -> list[dict[str, Any]]:
    """Query pending work items (v0.5.0: replaces actions table)."""
    return kernel.query_state(
        "work_items",
        status="pending",
        limit=limit,
        order="created_at_asc",
    )


def query_top_active_goals(*, limit: int = 5) -> list[dict[str, Any]]:
    """Top active goals ordered by importance × urgency.

    v1.0: reads from work_items(work_type='goal'); goals table dropped in Phase 4.
    """
    return kernel.query_state(
        "work_items", work_type="goal",
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


def recall_unified(
    query: str,
    *,
    k_memories: int = 3,
    k_knowledge: int = 3,
) -> list[dict]:
    """Unified semantic recall across memories AND knowledge documents.

    Combines kernel.recall_memory + kernel.recall_knowledge into a single
    ranked list. Each item carries source_type ("memory" | "document") and
    provenance (source field for memories, source_file metadata for documents).

    Implemented here (read_ports) rather than in the Kernel because it is a
    pure composition of the two existing recall ABI methods — keeping it out
    of the Kernel avoids growing the God Object (concept-zero-sum contract).
    """
    results: list[dict] = []

    try:
        for hit in kernel.recall_memory(query, k=k_memories):
            mem_id = hit.get("id") or ""
            provenance = ""
            if mem_id:
                rows = kernel.query_state("memories", id=mem_id)
                if rows:
                    provenance = rows[0].get("source", "") or ""
            results.append({
                "id": mem_id,
                "content": hit.get("content", ""),
                "source_type": "memory",
                "provenance": provenance,
                "distance": hit.get("distance"),
                "metadata": hit.get("metadata") or {},
            })
    except Exception:
        logger.warning("recall_unified: memory recall failed", exc_info=True)

    try:
        for hit in kernel.recall_knowledge(query, k=k_knowledge):
            meta = hit.get("metadata") or {}
            results.append({
                "id": hit.get("id") or "",
                "content": hit.get("content", ""),
                "source_type": "document",
                "provenance": meta.get("source_file", ""),
                "distance": hit.get("distance"),
                "metadata": meta,
            })
    except Exception:
        logger.warning("recall_unified: knowledge recall failed", exc_info=True)

    def _rank_key(item: dict) -> float:
        d = item.get("distance")
        return d if d is not None else float("inf")

    results.sort(key=_rank_key)
    return results


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


def retrieve_unified_with_sources(
    query: str,
    *,
    max_memories: int = 3,
    max_knowledge: int = 3,
) -> tuple[str, list[dict]]:
    """Unified retrieval across memories AND knowledge documents.

    Returns (context_str, sources) where sources may contain both:
      - {"type": "memory", "id": ..., "title": ...}
      - {"type": "document", "id": ..., "title": <filename>}

    The context_str renders a "## 相关记忆" section followed by a
    "## 相关文档" section so the LLM sees both, and the frontend can
    surface both as citations via the sources event.
    """
    if not query or len(query.strip()) < 2:
        return "", []

    unified = recall_unified(query, k_memories=max_memories, k_knowledge=max_knowledge)

    mem_items = [u for u in unified if u.get("source_type") == "memory"]
    doc_items = [u for u in unified if u.get("source_type") == "document"]

    parts: list[str] = []
    sources: list[dict] = []

    if mem_items:
        lines = ["## 相关记忆"]
        for i, mem in enumerate(mem_items, 1):
            lines.append(f"{i}. {mem.get('content', '')}")
        parts.append("\n".join(lines))
        sources.extend(
            {"id": m.get("id", ""), "type": "memory", "title": (m.get("content", "") or "")[:80]}
            for m in mem_items
            if m.get("id")
        )

    if doc_items:
        lines = ["## 相关文档"]
        for i, doc in enumerate(doc_items, 1):
            fname = doc.get("provenance") or "document"
            snippet = (doc.get("content", "") or "")[:300].strip().replace("\n", " ")
            lines.append(f"{i}. [{fname}] {snippet}")
        parts.append("\n".join(lines))
        sources.extend(
            {
                "id": d.get("id", ""),
                "type": "document",
                "title": d.get("provenance") or "document",
            }
            for d in doc_items
            if d.get("id")
        )

    return ("\n\n".join(parts), sources) if parts else ("", [])


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
    """Count active goals with no recent activity.

    v1.0 Phase 3b: prefers work_items(work_type='goal'), falls back to goals.
    """
    try:
        rows = kernel.query_state(
            "work_items", work_type="goal", status="active",
            last_activity_older_than_days=days, limit=10,
        )
        return len(rows)
    except Exception:
        return 0

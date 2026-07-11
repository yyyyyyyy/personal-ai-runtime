"""Runtime Read Ports — Fragment-facing read abstractions.

Fragments must use these ports instead of opening DB sessions,
importing ORM models, or calling Kernel / storage directly.

    Fragment → Read Port → Kernel → Projection / Query Model
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any

from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


def _kernel():
    """Resolve Kernel at call time (supports test patches / RuntimeContainer.reset)."""
    from app.core.runtime.kernel_instance import kernel as k
    return k


def _qb():
    from app.core.runtime.kernel import query_builder as qb
    return qb


def _db():
    return _kernel()._db


def query_pending_actions(*, limit: int = 5) -> list[dict[str, Any]]:
    """Query pending work items (v0.5.0: replaces actions table)."""
    return _kernel().query_state(
        "work_items",
        status="pending",
        limit=limit,
        order="created_at_asc",
    )


def query_top_active_goals(*, limit: int = 5) -> list[dict[str, Any]]:
    """Top active goals ordered by importance × urgency.

    v1.0: reads from work_items(work_type='goal'); goals table dropped in Phase 4.
    """
    return _kernel().query_state(
        "work_items", work_type="goal",
        status_in=("active", "in_progress"),
        limit=limit,
        order="importance_urgency_desc",
    )


def query_conversation_messages(
    conversation_id: str,
    *,
    limit: int = 20,
    order: str = "created_at_desc",
) -> list[dict[str, Any]]:
    return _kernel().query_state(
        "messages",
        conversation_id=conversation_id,
        limit=limit,
        order=order,
    )


def query_recent_inbox_emails(*, limit: int = 20) -> list[dict[str, Any]]:
    return _kernel().query_state(
        "inbox_emails",
        status_not="archived",
        limit=limit,
        order="date_desc",
    )


def search_inbox_emails(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    return _kernel().query_state(
        "inbox_emails",
        search=query,
        limit=limit,
        order="date_desc",
    )


def query_recent_legacy_events(*, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    return recent_events(
        _kernel().read_events,
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

    Combines _kernel().recall_memory + _kernel().recall_knowledge into a single
    ranked list. Each item carries source_type ("memory" | "document") and
    provenance (source field for memories, source_file metadata for documents).

    Implemented here (read_ports) rather than in the Kernel because it is a
    pure composition of the two existing recall ABI methods — keeping it out
    of the Kernel avoids growing the God Object (concept-zero-sum contract).
    """
    results: list[dict] = []

    try:
        for hit in _kernel().recall_memory(query, k=k_memories):
            mem_id = hit.get("id") or ""
            provenance = ""
            if mem_id:
                rows = _kernel().query_state("memories", id=mem_id)
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
        for hit in _kernel().recall_knowledge(query, k=k_knowledge):
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
    return _kernel().recall_knowledge(query, k=n_results)


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
        rows = _kernel().query_state("approvals", status="pending", limit=50)
        return len(rows)
    except Exception:
        return 0


def query_pending_approvals(*, limit: int = 50) -> list[dict[str, Any]]:
    """List pending approvals (Work / Capability deferrals awaiting the user)."""
    return _kernel().query_state("approvals", status="pending", limit=limit)


def query_pending_inbox_emails(*, limit: int = 50) -> list[dict[str, Any]]:
    """Pending inbox rows — state gate for email backlog reactions / nudges."""
    return _kernel().query_state(
        "inbox_emails", status="pending", limit=limit, order="date_desc",
    )


def query_stagnant_goals(*, days: int = 3, limit: int = 10) -> list[dict[str, Any]]:
    """Active goals with no recent activity (Work subtype work_type=goal)."""
    return _kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        last_activity_older_than_days=days,
        limit=limit,
    )


def query_llm_calls(*, days: int | None = None, limit: int = 5000, offset: int = 0) -> list[dict[str, Any]]:
    """Governed llm_calls projection via Kernel ABI."""
    filters: dict[str, Any] = {"limit": limit, "offset": offset}
    if days is not None:
        filters["since_days"] = days
    return _kernel().query_state("llm_calls", **filters)


def query_tool_calls(
    *,
    days: int | None = None,
    tool_name: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Governed tool_calls projection via Kernel ABI."""
    filters: dict[str, Any] = {"limit": limit}
    if days is not None:
        filters["since_days"] = days
    if tool_name:
        filters["tool_name"] = tool_name
    return _kernel().query_state("tool_calls", **filters)


def query_recent_tool_names(*, limit: int = 3) -> list[str]:
    """Return the names of the most recently invoked capabilities."""
    try:
        events = _kernel().read_events(type="CapabilityInvoked", limit=limit, order="desc")
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
        return len(query_stagnant_goals(days=days, limit=10))
    except Exception:
        return 0


# ── Work / Goals ──────────────────────────────────────────────────────────


def query_work_item(item_id: str) -> dict[str, Any] | None:
    """Fetch a single work_items row by id."""
    rows = _kernel().query_state("work_items", id=item_id, limit=1)
    return rows[0] if rows else None


def query_work_items(**filters: Any) -> list[dict[str, Any]]:
    """Pass-through work_items query — prefer more specific helpers when possible."""
    return _kernel().query_state("work_items", **filters)


def query_goals(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List goals (work_type=goal). Replaces the legacy ``goals`` selector."""
    filters: dict[str, Any] = {"work_type": "goal", "limit": limit}
    if status:
        filters["status"] = status
    return _kernel().query_state("work_items", **filters)


def query_goal(goal_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("work_items", work_type="goal", id=goal_id, limit=1)
    return rows[0] if rows else None


def query_goal_actions(goal_id: str) -> list[dict[str, Any]]:
    """Child actions of a goal."""
    return _kernel().query_state(
        "work_items", parent_goal_id=goal_id, work_type="action",
    )


def query_work_items_by_parent_goal(
    goal_id: str,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    return _kernel().query_state("work_items", parent_goal_id=goal_id, limit=limit)


def query_active_goals(
    *,
    limit: int = 20,
    order: str = "importance_desc",
) -> list[dict[str, Any]]:
    return _kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        limit=limit,
        order=order,
    )


def query_completed_goals(
    *,
    limit: int = 5000,
    updated_since: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {
        "work_type": "goal",
        "status": "completed",
        "limit": limit,
    }
    if updated_since:
        filters["updated_since"] = updated_since
    return _kernel().query_state("work_items", **filters)


def query_goals_with_deadline(*, limit: int = 500) -> list[dict[str, Any]]:
    """Active goals that have a deadline set."""
    return _kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        has_deadline=True,
        limit=limit,
    )


# ── Conversations / Messages ──────────────────────────────────────────────


def query_conversation(conversation_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("conversations", id=conversation_id, limit=1)
    return rows[0] if rows else None


def query_conversations(*, limit: int = 50) -> list[dict[str, Any]]:
    return _kernel().query_state("conversations", limit=limit)


def query_message(message_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("messages", id=message_id, limit=1)
    return rows[0] if rows else None


# ── User profile ──────────────────────────────────────────────────────────


def query_user_profile_category(category: str) -> dict[str, Any] | None:
    rows = _qb().query_user_profile(_db(), {"id": category, "limit": 1})
    return rows[0] if rows else None


def query_user_profile(*, limit: int = 50) -> list[dict[str, Any]]:
    return _qb().query_user_profile(_db(), {"limit": limit})


# ── Memories ──────────────────────────────────────────────────────────────


def query_memory(memory_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("memories", id=memory_id, limit=1)
    return rows[0] if rows else None


def query_memories(
    *,
    category: str | None = None,
    limit: int = 5000,
    order: str | None = None,
    confidence_gt: float | None = None,
    confidence_lt: float | None = None,
    decay_eligible: bool | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if category:
        filters["category"] = category
    if order:
        filters["order"] = order
    if confidence_gt is not None:
        filters["confidence_gt"] = confidence_gt
    if confidence_lt is not None:
        filters["confidence_lt"] = confidence_lt
    if decay_eligible is not None:
        filters["decay_eligible"] = decay_eligible
    return _kernel().query_state("memories", **filters)


# ── Notifications ─────────────────────────────────────────────────────────


def query_notification(notification_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("notifications", id=notification_id, limit=1)
    return rows[0] if rows else None


def query_notifications(
    *,
    unread_only: bool = False,
    limit: int = 50,
    type: str | None = None,
    title: str | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if unread_only:
        filters["unread_only"] = True
    if type:
        filters["type"] = type
    if title is not None:
        filters["title"] = title
    if order:
        filters["order"] = order
    return _kernel().query_state("notifications", **filters)


# ── Approvals ─────────────────────────────────────────────────────────────


def query_approval(approval_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("approvals", id=approval_id, limit=1)
    return rows[0] if rows else None


def query_approvals(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if status:
        filters["status"] = status
    return _kernel().query_state("approvals", **filters)


# ── Inbox ─────────────────────────────────────────────────────────────────


def query_inbox_email(email_id: str) -> dict[str, Any] | None:
    rows = _kernel().query_state("inbox_emails", id=email_id, limit=1)
    return rows[0] if rows else None


def query_inbox_emails(
    *,
    category: str | None = None,
    status: str | None = None,
    digested: int | None = None,
    limit: int = 50,
    order: str = "date_desc",
) -> list[dict[str, Any]]:
    """Flexible inbox projection reader used by product/inbox and APIs."""
    filters: dict[str, Any] = {"limit": limit, "order": order}
    if category:
        filters["category"] = category
    if status and status != "all":
        filters["status"] = status
    if digested is not None:
        filters["digested"] = digested
    return _kernel().query_state("inbox_emails", **filters)


# ── Background tasks ──────────────────────────────────────────────────────


def query_background_task(task_id: str) -> dict[str, Any] | None:
    rows = _qb().query_background_tasks(_db(), {"id": task_id, "limit": 1})
    return rows[0] if rows else None


def query_background_tasks(
    *,
    status: str | None = None,
    limit: int = 50,
    order: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if status:
        filters["status"] = status
    if order:
        filters["order"] = order
    return _qb().query_background_tasks(_db(), filters)


# ── Timers / Policy / pending work ────────────────────────────────────────


def query_active_timers(*, limit: int = 100) -> list[dict[str, Any]]:
    return _qb().query_timer_events(_db(), {"status": "active", "limit": limit})


def query_timer(timer_id: str) -> dict[str, Any] | None:
    rows = _qb().query_timer_events(_db(), {"id": timer_id, "limit": 1})
    return rows[0] if rows else None


def query_due_timers(*, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
    """Active timers whose fire_at is at or before now_iso."""
    return _qb().query_timer_events(
        _db(),
        {"status": "active", "fire_at_lt": now_iso, "limit": limit},
    )


def query_active_policies(*, limit: int = 200) -> list[dict[str, Any]]:
    return _kernel().query_state("policy_events", status="active", limit=limit)


def query_pending_work_items(*, limit: int = 100) -> list[dict[str, Any]]:
    return _kernel().query_state("work_items", status="pending", limit=limit)


# ── Event formatting (folded from event_formatting.py) ───────────────────

_LEGACY_TYPE: dict[str, str] = {
    "ActionCreated": "action_created",
    "ActionUpdated": "action_status_changed",
    "ActionDeleted": "action_deleted",
    "WorkItemCreated": "task_created",
    "WorkItemUpdated": "task_status_changed",
    "WorkItemStatusChanged": "task_status_changed",
    "WorkItemDeleted": "task_status_changed",
    "CapabilityInvoked": "tool_call",
    "ApprovalRequested": "approval_requested",
    "ApprovalGranted": "approval_granted",
    "ApprovalDenied": "approval_denied",
    "TaskCreated": "task_created",
    "TaskCompleted": "task_completed",
    "TaskFailed": "task_failed",
    "TaskStatusChanged": "task_status_changed",
    "MemoryDerived": "memory_derived",
    "ConversationRecorded": "conversation",
}


def _goal_id_for(event: Event) -> str | None:
    """Extract goal_id from an event's aggregate or payload.

    v1.0: Goal aggregate retired. goal_id comes from work_item payload or parent_goal_id.
    """
    if event.aggregate_type == "work_item":
        return event.payload.get("parent_goal_id") or event.aggregate_id
    if event.aggregate_type in ("action"):
        return event.payload.get("goal_id") or event.payload.get("parent_goal_id")
    return event.payload.get("goal_id")


def _summary_for(event: Event) -> str:
    """Generate a human-readable summary string for an event."""
    p = event.payload
    t = event.type
    if t == "ActionCreated":
        return f"Action created: {p.get('title', '')}"
    if t == "ActionUpdated":
        return f"Action status -> {p.get('status', '')}"
    if t == "CapabilityInvoked":
        return f"Tool called: {p.get('name', '')}"
    if t == "ApprovalRequested":
        return f"Approval requested: {p.get('action', '')}"
    if t == "ApprovalGranted":
        return f"Approval granted: {p.get('action', '')}"
    if t == "ApprovalDenied":
        return f"Approval denied: {p.get('action', '')}"
    if t == "TaskCreated":
        return f"Task created: {p.get('name', '')}"
    if t in ("TaskCompleted", "TaskFailed", "TaskStatusChanged"):
        return f"Task {p.get('status', t)}: {event.aggregate_id}"
    if t == "WorkItemCreated":
        return f"WorkItem created: {p.get('title', '')}"
    if t in ("WorkItemStatusChanged", "WorkItemUpdated"):
        return f"WorkItem {p.get('status', t)}: {event.aggregate_id}"
    if t == "MemoryDerived":
        return f"Memory derived: {str(p.get('content', ''))[:60]}"
    if t == "ConversationRecorded":
        return f"Conversation: {str(p.get('user_message', ''))[:60]}"
    return f"{t}: {event.aggregate_id}"


def to_legacy_dict(event: Event) -> dict:
    """Convert a Kernel Event to a UI-friendly dict shape."""
    legacy_type = _LEGACY_TYPE.get(event.type, event.type.lower())
    payload = event.payload or {}
    return {
        "id": event.id,
        "type": legacy_type,
        "summary": _summary_for(event),
        "goal_id": _goal_id_for(event),
        "payload": json.dumps(payload) if payload else None,
        "timestamp": event.ts,
    }


def goal_events(goal_id: str, *, limit: int = 20) -> list[dict]:
    """Return goal-scoped events from event_log (goal + related actions/work_items)."""
    from app.core.runtime.kernel_instance import kernel

    goal_ev = kernel.read_events(
        aggregate_type="goal", aggregate_id=goal_id, order="desc", limit=limit,
    )
    action_ev = kernel.read_events(
        aggregate_type="action", payload_goal_id=goal_id,
        order="desc", limit=limit,
    )
    # work_item: the goal's own events (aggregate_id == goal_id) plus children
    # linked via payload.parent_goal_id.
    own_ev = kernel.read_events(
        aggregate_type="work_item", aggregate_id=goal_id, order="desc", limit=limit,
    )
    child_ev = kernel.read_events(
        aggregate_type="work_item", payload_goal_id=goal_id,
        order="desc", limit=limit,
    )
    combined = sorted(goal_ev + action_ev + own_ev + child_ev, key=lambda e: e.seq or 0, reverse=True)[:limit]
    return [to_legacy_dict(e) for e in combined]


def recent_events(
    read_fn,
    *,
    days: int = 7,
    limit: int = 50,
    event_type: str | None = None,
    goal_id: str | None = None,
) -> list[dict]:
    """Read recent events from event_log and return UI-friendly rows."""
    since_ts = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    filters: dict = {"since_ts": since_ts, "limit": limit, "order": "desc"}
    if event_type:
        filters["type"] = event_type

    events = read_fn(**filters)
    rows = [to_legacy_dict(e) for e in events]

    if goal_id:
        rows = [r for r in rows if r.get("goal_id") == goal_id]

    return rows[:limit]

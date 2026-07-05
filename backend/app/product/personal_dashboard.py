"""Personal Dashboard — pure Runtime ABI product (consistency slice).

This product is the "一致性测试床" — it proves the Runtime can natively host
a product feature without any boundary violations. Every data access goes
through Kernel ABI (query_state, read_events, recall_memory).

No SQL. No file system access. No direct ChromaDB access. Zero bypasses.

Widgets:
  - data_sovereignty: total events, memories (self-report/claim), goals, conversations
  - active_goals: active goal count + top 3 by importance
  - recent_events: last 5 system events (what happened)
  - recent_memories: semantic recall of recent beliefs
  - timer_status: active timer count (Time dimension)
  - governance_status: active policy + grant counts (Governance)
"""

from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel_instance import kernel
from app.store.database import db

# Maximum items per widget
_MAX_RECENT_EVENTS = 10
_MAX_RECENT_MEMORIES = 5
_MAX_TOP_GOALS = 3


def generate_dashboard() -> dict:
    """Generate a Personal Dashboard using only Kernel ABI.

    This function proves a product can be built without bypassing Runtime
    boundaries. Every read goes through kernel.query_state / read_events /
    recall_memory.
    """
    now = datetime.now(UTC)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    return {
        "generated_at": now.isoformat(),
        "data_sovereignty": _widget_data_sovereignty(),
        "active_goals": _widget_active_goals(),
        "recent_events": _widget_recent_events(seven_days_ago),
        "recent_memories": _widget_recent_memories(),
        "timer_status": _widget_timer_status(),
        "governance_status": _widget_governance_status(),
    }


def _widget_data_sovereignty() -> dict:
    """Data sovereignty overview — user's personal data footprint.

    Every data query goes through Kernel ABI only.
    """
    try:
        table_counts = kernel.table_counts(
            ("conversations", "messages", "goals", "memories", "event_log")
        )
    except Exception:
        table_counts = {}

    # Count self-report vs claim memories
    try:
        memories = kernel.query_state("memories", limit=5000)
        self_report_count = sum(1 for m in memories if m.get("origin") == "self_report")
        claim_count = sum(1 for m in memories if m.get("origin") == "claim")
    except Exception:
        memories = []
        self_report_count = 0
        claim_count = 0

    # Active vs completed goals (v1.0 Phase 4: goals table retired)
    try:
        goals_active = kernel.query_state(
            "work_items", work_type="goal", status="active", limit=5000,
        )
        goals_completed = kernel.query_state(
            "work_items", work_type="goal", status="completed", limit=5000,
        )
    except Exception:
        goals_active = []
        goals_completed = []

    # Last belief reflection time
    try:
        beliefs = kernel.query_state("memories", category="belief", limit=5, order="created_desc")
        last_reflection = beliefs[0].get("created_at") if beliefs else None
    except Exception:
        last_reflection = None

    return {
        "total_events": table_counts.get("event_log", 0),
        "total_memories": table_counts.get("memories", 0),
        "memories_self_report": self_report_count,
        "memories_claim": claim_count,
        "total_goals": table_counts.get("goals", 0),
        "goals_active": len(goals_active),
        "goals_completed": len(goals_completed),
        "total_conversations": table_counts.get("conversations", 0),
        "total_messages": table_counts.get("messages", 0),
        "data_location": "本地存储 (SQLite + ChromaDB)",
        "last_belief_reflection": last_reflection,
        "export_supported": True,
    }


def _widget_active_goals() -> dict:
    """Active goals — count + top by importance (v1.0: unified work_items)."""
    active = kernel.query_state(
        "work_items", work_type="goal", status="active",
        limit=50, order="importance_desc",
    )
    top = active[:_MAX_TOP_GOALS]
    return {
        "count": len(active),
        "top": [
            {
                "id": g.get("id", ""),
                "title": g.get("title", ""),
                "progress": g.get("progress", 0),
                "importance": g.get("importance", 0),
            }
            for g in top
        ],
    }


def _widget_recent_events(since_ts: str) -> dict:
    """Recent system events — what happened (read_events only)."""
    # Get the last N events from the Event Log
    all_events = kernel.read_events(since_ts=since_ts, limit=_MAX_RECENT_EVENTS, order="desc")
    # Filter out internal/chatter events for a cleaner dashboard
    interesting = [e for e in all_events if e.type not in {
        "ChatTextDelta", "ChatDone",
    }]
    top_events = interesting[:_MAX_RECENT_EVENTS]
    return {
        "count": len(top_events),
        "total_in_window": len(all_events),
        "items": [
            {
                "seq": e.seq,
                "type": e.type,
                "actor": e.actor,
                "ts": e.ts,
            }
            for e in top_events
        ],
    }


def _widget_recent_memories() -> dict:
    """Recent beliefs — what the system thinks it knows (recall_memory only)."""
    # Semantic recall for a general summary of what the user cares about
    memories = kernel.recall_memory("recent activities goals preferences", k=_MAX_RECENT_MEMORIES)
    return {
        "count": len(memories),
        "items": [
            {
                "content": m.get("content", "")[:200],
                "category": m.get("category", ""),
                "confidence": m.get("confidence", 0),
            }
            for m in memories
        ],
    }


def _widget_timer_status() -> dict:
    """Active timers — Time dimension health (query_state only)."""
    try:
        active = kernel.query_state("timer_events", status="active", limit=100)
    except Exception:
        return {"active_timers": 0, "items": []}
    return {
        "active_timers": len(active),
        "items": [
            {
                "handler_name": t.get("handler_name", ""),
                "schedule_type": t.get("schedule_type", ""),
                "fire_at": t.get("fire_at", ""),
            }
            for t in active[:5]
        ],
    }


def _widget_governance_status() -> dict:
    """Policy status — Governance Runtime health (query_state only).

    v0.9.0: grant_events reporting removed — table has no projector writer
    since v0.7.0, so the count was always 0. active_grants kept in the
    response shape for frontend backward-compat but is hardcoded 0.
    """
    try:
        policies = kernel.query_state("policy_events", status="active", limit=200)
    except Exception:
        policies = []
    return {
        "active_policies": len(policies),
        "active_grants": 0,
    }

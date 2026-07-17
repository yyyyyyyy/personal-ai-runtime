"""Personal Dashboard — pure Runtime ABI product (consistency slice).

This product is the "一致性测试床" — it proves the Runtime can natively host
a product feature without any boundary violations. Every data access goes
through read_ports → Kernel ABI (query_state, read_events, recall_memory).

No SQL. No file system access. No direct ChromaDB access. Zero bypasses.

Widgets:
  - data_sovereignty: total events, memories (self-report/claim), goals, conversations
  - active_goals: active goal count + top 3 by importance
  - recent_events: last 5 system events (what happened)
  - recent_memories: semantic recall of recent beliefs
  - timer_status: active timer count (Time dimension)
  - governance_status: active policy + grant counts (Governance)
"""

import logging
from datetime import UTC, datetime, timedelta

from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)

# Maximum items per widget
_MAX_RECENT_EVENTS = 10
_MAX_RECENT_MEMORIES = 5
_MAX_TOP_GOALS = 3


def generate_dashboard() -> dict:
    """Generate a Personal Dashboard using only Kernel ABI via read_ports.

    Widgets run sequentially: SQLite is fine with thread-local connections, but
    Chroma/HNSW (``recall_memory``) is not safe under concurrent native access
    and has segfaulted CI under ThreadPoolExecutor + TestClient.
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
    """Data sovereignty overview — user's personal data footprint."""
    try:
        table_counts = kernel.table_counts(
            ("conversations", "messages", "memories", "event_log")
        )
    except Exception:
        logger.warning("Dashboard: Failed to fetch table_counts", exc_info=True)
        table_counts = {}

    try:
        goal_total = read_ports.count_goals()
    except Exception:
        logger.warning("Dashboard: Failed to fetch total goals count", exc_info=True)
        goal_total = 0

    try:
        self_report_count = read_ports.count_memories(origin="self_report")
        claim_count = read_ports.count_memories(origin="claim")
    except Exception:
        logger.warning("Dashboard: Failed to fetch memories footprint", exc_info=True)
        self_report_count = 0
        claim_count = 0

    try:
        goals_active = read_ports.count_active_goals()
        goals_completed = read_ports.count_completed_goals()
    except Exception:
        logger.warning("Dashboard: Failed to fetch active/completed goals count", exc_info=True)
        goals_active = 0
        goals_completed = 0

    try:
        beliefs = read_ports.query_memories(category="belief", limit=1, order="created_desc")
        last_reflection = beliefs[0].get("created_at") if beliefs else None
    except Exception:
        logger.warning("Dashboard: Failed to fetch last reflection", exc_info=True)
        last_reflection = None

    return {
        "total_events": table_counts.get("event_log", 0),
        "total_memories": table_counts.get("memories", 0),
        "memories_self_report": self_report_count,
        "memories_claim": claim_count,
        "total_goals": goal_total,
        "goals_active": goals_active,
        "goals_completed": goals_completed,
        "total_conversations": table_counts.get("conversations", 0),
        "total_messages": table_counts.get("messages", 0),
        "data_location": "本地存储 (SQLite + ChromaDB)",
        "last_belief_reflection": last_reflection,
        "export_supported": True,
    }


def _widget_active_goals() -> dict:
    """Active goals — count + top by importance."""
    try:
        active_count = read_ports.count_active_goals()
        top = read_ports.query_active_goals(limit=_MAX_TOP_GOALS, order="importance_desc")
    except Exception:
        logger.warning("Dashboard: Failed to fetch active goals widget", exc_info=True)
        return {"count": 0, "top": []}

    return {
        "count": active_count,
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
    try:
        all_events = kernel.read_events(since_ts=since_ts, limit=_MAX_RECENT_EVENTS * 5, order="desc")
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
    except Exception:
        logger.warning("Dashboard: Failed to fetch recent events widget", exc_info=True)
        return {"count": 0, "total_in_window": 0, "items": []}


def _widget_recent_memories() -> dict:
    """Recent beliefs — what the system thinks it knows (recall_memory only)."""
    try:
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
    except Exception:
        logger.warning("Dashboard: Failed to fetch recent memories widget", exc_info=True)
        return {"count": 0, "items": []}


def _widget_timer_status() -> dict:
    """Active timers — Time dimension health."""
    try:
        active = read_ports.query_active_timers(limit=100)
    except Exception:
        logger.warning("Dashboard: Failed to fetch timer status widget", exc_info=True)
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
    """Policy status — Governance Runtime health.

    ``active_grants`` is kept in the response shape (hardcoded 0) for
    frontend compatibility.
    """
    try:
        policies = read_ports.query_active_policies(limit=200)
    except Exception:
        logger.warning("Dashboard: Failed to fetch governance status widget", exc_info=True)
        policies = []
    return {
        "active_policies": len(policies),
        "active_grants": 0,
    }

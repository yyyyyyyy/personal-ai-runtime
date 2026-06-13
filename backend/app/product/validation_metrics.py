"""User validation metrics — supports USER_VALIDATION.md retention tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.runtime.kernel.constants import (
    EVENT_CONVERSATION_CREATED,
    EVENT_MESSAGE_APPENDED,
)
from app.core.runtime.kernel_instance import kernel
from app.product.friction_log import friction_stats
from app.store.database import db


def get_validation_metrics() -> dict:
    """Return dogfood-oriented metrics for self-use validation."""
    counts = kernel.table_counts(("conversations", "messages"))
    since = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    conv_events = kernel.read_events(type=EVENT_CONVERSATION_CREATED, since_ts=since)
    msg_events = kernel.read_events(type=EVENT_MESSAGE_APPENDED, since_ts=since)

    user_messages_7d = 0
    active_days: set[str] = set()
    for event in msg_events:
        payload = event.payload or {}
        if payload.get("role") != "user":
            continue
        user_messages_7d += 1
        if event.ts:
            active_days.add(event.ts[:10])

    with db.get_db() as conn:
        export_count = conn.execute(
            "SELECT COUNT(*) as c FROM activity_log WHERE type = 'persona_export'"
        ).fetchone()["c"]

    conversations_7d = len({event.aggregate_id for event in conv_events})
    friction = friction_stats(since_days=7)

    return {
        "mode": "dogfood",
        "total_conversations": counts.get("conversations", 0),
        "conversations_7d": conversations_7d,
        "active_chat_days_7d": len(active_days),
        "user_messages_7d": user_messages_7d,
        "export_count": export_count,
        "friction": friction,
        "targets": {
            "active_days_per_week": 3,
            "export_at_least_once": True,
            "friction_logged_when_bad": True,
        },
    }

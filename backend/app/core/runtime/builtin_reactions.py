"""Built-in Reactions — declarative event→action bindings.

v0.6.0: Replaces the old trigger_engine.seed_builtin_triggers().
Each reaction below is registered via the @reaction decorator at import time.
"""

from app.core.runtime.reaction_registry import (
    ReactionThen,
    ReactionWhen,
    get_reaction_registry,
    reaction,
)

# ── Email backlog ─────────────────────────────────────────────────────────

@reaction(
    when=ReactionWhen(event_type="InboxEmailRecorded", count_gte=50, window_days=1),
    then=ReactionThen(
        notification_template="收件箱积压 {count} 封邮件，需要整理吗？",
        notification_severity="warning",
    ),
)
def email_backlog_50(event_or_kernel=None) -> None:
    """Notify when 50+ emails accumulate within 1 day."""
    from app.core.runtime.notification_bridge import push_notification
    push_notification("suggestion", "收件箱整理建议", "收件箱积压较多，建议花几分钟整理。")
    import logging
    logging.getLogger(__name__).info("Reaction fired: email_backlog_50")


# ── Goal staleness ────────────────────────────────────────────────────────

def _register_staleness_reactions():
    """Register staleness-check reactions triggered by periodic evaluation."""

    registry = get_reaction_registry()

    # Goal staleness reaction: fired periodically by RuntimeLoop._maintenance
    from app.core.runtime.reaction_registry import Reaction, ReactionWhen
    registry.register(Reaction(
        name="goal_staleness_check",
        when=ReactionWhen(count_gte=1),  # always evaluated in cycle
        handler=_check_stagnant_goals,
    ))


def _check_stagnant_goals(kernel=None) -> None:
    """Check for goals with no recent activity and create notifications."""
    from datetime import UTC, datetime

    from app.core.runtime.kernel_instance import kernel as k
    kern = kernel or k

    # v1.0 Phase 3b: prefer work_items(work_type='goal'), fall back to goals.
    stagnant = kern.query_state(
        "work_items", work_type="goal", status="active",
        last_activity_older_than_days=3, limit=5,
    )
    if not stagnant:
        stagnant = kern.query_state(
            "goals", status="active",
            last_activity_older_than_days=3, limit=5,
        )
    import logging
    logger = logging.getLogger(__name__)

    for goal in stagnant:
        goal_id = goal.get("id", "")
        title = goal.get("title", "")
        last_activity = goal.get("last_activity_at") or goal.get("created_at", "")

        existing = kern.query_state(
            "notifications", related_id=goal_id,
            notification_type="goal_stagnant", limit=1,
        )
        if existing:
            notif_time = existing[0].get("created_at", "")
            if notif_time > last_activity:
                continue

        try:
            activity_dt = datetime.fromisoformat(last_activity)
            days_stagnant = (datetime.now(UTC) - activity_dt).days
        except (ValueError, TypeError):
            days_stagnant = 3

        kern.emit_event(
            "NotificationCreated", "notification", f"notif_stagnant_{goal_id}",
            payload={
                "type": "goal_stagnant",
                "title": f"目标停滞: {title}",
                "content": f"目标已 {days_stagnant} 天未更新，需要关注",
                "severity": "warning",
                "related_id": goal_id,
                "related_type": "goal",
                "notification_type": "goal_stagnant",
            },
            actor="system",
        )
        logger.info("Created stagnant goal notification for: %s", title)


# Register staleness reactions on import
_register_staleness_reactions()

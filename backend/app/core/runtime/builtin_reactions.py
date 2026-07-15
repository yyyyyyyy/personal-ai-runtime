"""Built-in Reactions — declarative event→action bindings.

``ReactionWhen.every_cycle`` + ``state_selector`` gate is evaluated by the registry.
Each reaction below is registered via the @reaction decorator at import time.
"""

from app.core.runtime.reaction_registry import (
    ReactionThen,
    ReactionWhen,
    get_reaction_registry,
    reaction,
)

# ── Email backlog ─────────────────────────────────────────────────────────

_EMAIL_BACKLOG_THRESHOLD = 50
_EMAIL_BACKLOG_NOTIF_TYPE = "suggestion"
_EMAIL_BACKLOG_NOTIF_TITLE = "收件箱整理建议"


@reaction(
    when=ReactionWhen(
        every_cycle=True,
        state_selector="inbox_emails",
        state_filters={"status": "pending"},
        count_gte=_EMAIL_BACKLOG_THRESHOLD,
        # Descriptive: InboxEmailRecorded feeds the pending inbox projection.
        event_type="InboxEmailRecorded",
    ),
    then=ReactionThen(
        notification_template="收件箱积压 {count} 封邮件，需要整理吗？",
        notification_severity="warning",
    ),
)
def email_backlog_50(kernel=None) -> None:
    """Notify when pending inbox emails reach the backlog threshold.

    ``evaluate_cycle`` already gates on pending inbox count >= threshold.
    This handler re-checks (defense in depth), dedupes, and notifies.
    """
    import logging

    from app.core.runtime.kernel_instance import kernel as default_kernel
    from app.product.notifications import find_notification

    logger = logging.getLogger(__name__)
    kern = kernel or default_kernel

    # Fetch one extra row so len == threshold reliably distinguishes
    # "exactly at threshold" from "truncated at threshold"; the displayed
    # count is therefore a lower bound when more are pending.
    pending = kern.query_state(
        "inbox_emails", status="pending", limit=_EMAIL_BACKLOG_THRESHOLD + 1,
    )
    count = len(pending)
    if count < _EMAIL_BACKLOG_THRESHOLD:
        return

    if find_notification(_EMAIL_BACKLOG_NOTIF_TYPE, _EMAIL_BACKLOG_NOTIF_TITLE, kernel=kern):
        logger.debug("email_backlog_50 already notified, skipping broadcast")
        return

    from app.core.runtime.notification_bridge import push_notification
    push_notification(
        _EMAIL_BACKLOG_NOTIF_TYPE,
        _EMAIL_BACKLOG_NOTIF_TITLE,
        f"收件箱积压 {count} 封邮件，需要整理吗？",
        kernel=kern,
    )
    logger.info("Reaction fired: email_backlog_50 (count=%d)", count)


# ── Goal staleness ────────────────────────────────────────────────────────

def _register_staleness_reactions():
    """Register staleness-check reactions triggered by periodic evaluation."""

    registry = get_reaction_registry()

    from app.core.runtime.reaction_registry import Reaction, ReactionWhen
    registry.register(Reaction(
        name="goal_staleness_check",
        when=ReactionWhen(every_cycle=True),
        handler=_check_stagnant_goals,
    ))


def _check_stagnant_goals(kernel=None) -> None:
    """Check for goals with no recent activity and create notifications."""
    from datetime import UTC, datetime

    from app.core.runtime.kernel_instance import kernel as k
    kern = kernel or k

    # Prefer work_items(work_type='goal'); goals selector is an alias.
    stagnant = kern.query_state(
        "work_items", work_type="goal", status="active",
        last_activity_older_than_days=3, limit=5,
    )

    import logging
    logger = logging.getLogger(__name__)

    for goal in stagnant:
        goal_id = goal.get("id", "")
        title = goal.get("title", "")
        created_at = goal.get("created_at", "")
        last_activity = goal.get("last_activity_at") or created_at

        # v1.0 Grace period: do not notify for goals created within the last 3 days
        # if they have no activity yet. last_activity_at is only set on updates.
        try:
            created_dt = datetime.fromisoformat(created_at)
            if (datetime.now(UTC) - created_dt).days < 3:
                continue
        except (ValueError, TypeError):
            pass

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

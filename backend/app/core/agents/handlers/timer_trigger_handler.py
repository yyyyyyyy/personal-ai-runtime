"""Timer trigger handler — subscribes to TimerFired and runs scheduled product work."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


async def _call_product(
    handler_name: str,
    payload: dict | None = None,
    timer_id: str | None = None,
) -> None:
    """Dispatch timer handler_name to the appropriate product function."""
    payload = payload or {}
    from datetime import UTC, datetime, timedelta, tzinfo
    from zoneinfo import ZoneInfo
    try:
        tz: tzinfo = ZoneInfo(settings.timezone)
    except Exception:
        tz = UTC

    try:
        if handler_name == "deadline_alert":
            from app.core.runtime import read_ports

            candidates = read_ports.query_goals_with_deadline(limit=500)
            now_local = datetime.now(tz)
            today = now_local.date()
            target_dates = {today + timedelta(days=offset) for offset in (1, 3)}
            for goal in candidates:
                if not goal.get("deadline"):
                    continue
                try:
                    deadline_dt = datetime.fromisoformat(goal["deadline"])
                    if deadline_dt.tzinfo is None:
                        deadline_dt = deadline_dt.replace(tzinfo=UTC)
                    deadline_local = deadline_dt.astimezone(tz)
                    deadline_date = deadline_local.date()
                except ValueError:
                    continue
                if deadline_date in target_dates:
                    days_left = (deadline_local.date() - today).days
                    from app.product.notifications import create_notification

                    create_notification(
                        "alert",
                        "Deadline 预警",
                        f"目标「{goal['title']}」还有 {days_left} 天截止",
                    )
        elif handler_name == "memory_decay":
            from app.core.runtime.cron_registry import run_memory_decay

            run_memory_decay()
        elif handler_name == "world_model_snapshot":
            from app.core.agents.world_model import world_model

            world_model.refresh_snapshot()
        elif handler_name == "projection_snapshots":
            from app.core.runtime.kernel_instance import kernel

            results = kernel.save_projection_snapshots()
            logger.info("Projection snapshots saved for %d aggregates", len(results))
        elif handler_name == "inbox_poll":
            await _run_inbox_poll()
        elif handler_name == "inbox_digest":
            from app.product.inbox import generate_inbox_digest

            digest = generate_inbox_digest()
            if digest:
                from app.core.runtime.notification_channel import notification_router
                summary = digest.get("summary", "") if isinstance(digest, dict) else str(digest)
                await notification_router.notify(
                    "收件箱摘要", summary[:500],
                    type_="inbox_digest",
                )
        elif handler_name == "morning_brief":
            from app.core.runtime import read_ports
            from app.core.runtime.notification_channel import notification_router

            now_local = datetime.now(tz)
            # Get today's calendar events
            try:
                calendar_items = read_ports.query_active_timers(limit=50)
            except Exception:
                calendar_items = []

            # Get goal summary
            try:
                active_goals = read_ports.query_active_goals(limit=10)

                goal_lines = "\n".join([f"  · {g.get('title', '')} (进度 {g.get('progress', 0)}%)" for g in active_goals[:5]]) if active_goals else "  无"
            except Exception:
                goal_lines = "  获取失败"

            # Get unread inbox count
            try:
                inbox_items = read_ports.query_inbox_emails(limit=500, status="new")
                inbox_count: int = len(inbox_items)
            except Exception:
                inbox_count = 0

            brief = (
                f"早安！{now_local.strftime('%Y年%m月%d日')} 简报\n\n"
                f"📋 进行中的目标:\n{goal_lines}\n\n"
                f"📧 未读邮件: {inbox_count} 封\n\n"
                f"⏰ 活跃定时任务: {len(calendar_items)} 个\n\n"
                f"祝你今天一切顺利！"
            )
            # Save persistent notification for Dashboard display
            from app.product.notifications import create_notification
            create_notification("morning_brief", "早安简报", brief)
            # Push via all notification channels (desktop, webhook, ntfy)
            await notification_router.notify("早安简报", brief, type_="morning_brief", priority="normal")
        elif handler_name == "reminder":
            from app.core.runtime.notification_channel import notification_router
            from app.product.notifications import create_notification

            message = payload.get("message", "时间到！")
            title = f"提醒: {message}" if len(message) < 20 else "提醒"
            # Include timer_id so create_notification idempotency doesn't collapse
            # consecutive reminders with the same message text.
            if timer_id:
                title = f"{title} ({timer_id})"

            create_notification("reminder", title, message)
            await notification_router.notify(title, message, type_="reminder", priority="high")
        else:
            logger.warning("Unknown timer handler: %s", handler_name)
    except Exception as e:
        logger.warning("Timer handler %s error: %s", handler_name, e)


async def _run_inbox_poll():
    """Inbox poll via fire-and-forget event emission.

    Emits InboxPollRequested without waiting for completion — the handler
    runs as its own WorkItem and reports back via InboxPollCompleted. This
    keeps the TimerFired WorkItem under its 30s timeout instead of nesting
    a synchronous submit_command that can never finish in time.
    """
    import uuid

    from app.core.runtime.agent_scheduler import ensure_scheduler, get_scheduler
    from app.core.runtime.kernel_instance import kernel

    await ensure_scheduler(kernel)
    sched = get_scheduler(kernel)
    await sched.start()
    kernel.emit_event(
        "InboxPollRequested",
        "inbox",
        f"inbox_poll_{uuid.uuid4().hex[:8]}",
        payload={"limit": 20},
        actor="scheduler",
    )


@subscribe("TimerFired")
async def on_timer_fired(ctx: "ExecutionContext", event: "Event") -> None:
    """TimerFired → execute product function in Execution context."""
    handler_name = event.payload.get("handler_name", "")
    payload = event.payload.get("payload", {})
    timer_id = event.aggregate_id
    if not handler_name:
        logger.warning("TimerFired without handler_name: %s", event.id)
        return
    await _call_product(handler_name, payload, timer_id)

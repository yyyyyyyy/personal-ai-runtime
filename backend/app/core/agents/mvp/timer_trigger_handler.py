"""Timer trigger handler — subscribes to TimerFired and runs scheduled product work."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.runtime.handler_registry import subscribe

if TYPE_CHECKING:
    from app.core.runtime.execution_context import ExecutionContext
    from app.core.runtime.kernel.event import Event

logger = logging.getLogger(__name__)


async def _call_product(handler_name: str) -> None:
    """Dispatch timer handler_name to the appropriate product function."""
    from datetime import UTC, datetime, timedelta

    try:
        if handler_name == "belief_reflection":
            from app.core.belief.belief_engine import ReflectionContext, belief_engine
            from app.core.runtime.kernel_instance import kernel

            patterns = kernel.query_state("patterns", window_days=14, limit=20)
            goals = kernel.query_state("goals", status="active", limit=10)
            memories = kernel.query_state("memories", confidence_gt=0.3, limit=20)
            if patterns:
                ctx_ref = ReflectionContext(patterns=patterns, goals=goals, memories=memories)
                beliefs = await belief_engine.reflect(ctx_ref)
                logger.info("Belief reflection produced %d beliefs", len(beliefs))
                if beliefs:
                    from app.core.runtime.notification_channel import notification_router
                    belief_summary = "\n".join([f"  · {b.get('content', '')[:80]}" for b in beliefs[:3]])
                    await notification_router.notify(
                        "AI 反思完成", f"产生了 {len(beliefs)} 条新认知:\n{belief_summary}",
                        type_="belief_reflection",
                    )
        elif handler_name == "deadline_alert":
            from app.core.runtime.kernel_instance import kernel

            candidates = kernel.query_state("goals", status="active", has_deadline=True, limit=500)
            today_utc = datetime.now(UTC).date()
            target_dates = {today_utc + timedelta(days=offset) for offset in (1, 3)}
            for goal in candidates:
                if not goal.get("deadline"):
                    continue
                try:
                    deadline_date = datetime.fromisoformat(goal["deadline"]).date()
                except ValueError:
                    continue
                if deadline_date in target_dates:
                    delta = datetime.fromisoformat(goal["deadline"]) - datetime.now(UTC)
                    days_left = delta.days
                    from app.product.notifications import create_notification

                    create_notification("alert", "Deadline 预警", f"目标「{goal['title']}」还有 {days_left} 天截止")
        elif handler_name == "trigger_evaluation":
            from app.core.runtime.trigger_engine import trigger_engine

            trigger_engine.evaluate_and_notify()
        elif handler_name == "memory_decay":
            from app.core.runtime.memory_decay import run_memory_decay

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
            from app.core.runtime.kernel_instance import kernel
            from app.core.runtime.notification_channel import notification_router

            now = datetime.now(UTC)
            # Get today's calendar events
            try:
                calendar_items = kernel.query_state("timer_events", status="active", limit=50)
            except Exception:
                calendar_items = []

            # Get goal summary
            try:
                active_goals = kernel.query_state("goals", status="active", limit=10)
                goal_lines = "\n".join([f"  · {g.get('title', '')} (进度 {g.get('progress', 0)}%)" for g in active_goals[:5]]) if active_goals else "  无"
            except Exception:
                goal_lines = "  获取失败"

            # Get unread inbox count
            try:
                inbox_items = kernel.query_state("inbox_emails", limit=500, status="new")
                inbox_count: int = len(inbox_items)
            except Exception:
                inbox_count = 0

            brief = (
                f"早安！{now.strftime('%Y年%m月%d日')} 简报\n\n"
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

    from app.core.runtime.agent_bootstrap import ensure_agent
    from app.core.runtime.agent_scheduler import get_scheduler
    from app.core.runtime.kernel_instance import kernel

    await ensure_agent(kernel)
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
    if not handler_name:
        logger.warning("TimerFired without handler_name: %s", event.id)
        return
    await _call_product(handler_name)

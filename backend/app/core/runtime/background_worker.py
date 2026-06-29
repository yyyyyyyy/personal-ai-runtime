"""Background Worker — executes long-running background tasks via Kernel."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from app.core.agents.critic import critic as _critic
from app.core.runtime.kernel.constants import (
    AGGREGATE_BACKGROUND_TASK,
    AGGREGATE_NOTIFICATION,
    EVENT_BG_TASK_CREATED,
    EVENT_BG_TASK_STATUS_CHANGED,
    EVENT_NOTIFICATION_CREATED,
)
from app.core.runtime.kernel_instance import kernel
from app.store.database import db

logger = logging.getLogger(__name__)

REPLAN_MAX_ATTEMPTS = 2  # Max replan attempts per task


class BackgroundWorker:
    """Polls background_tasks table and executes pending long-running tasks."""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self):
        while self._running:
            try:
                await kernel.agent_registry.cleanup_stale()
                await self._expire_stale_approvals()
                await self._smart_notification_check()
                await self._process_pending()
            except Exception:
                logger.exception("Background worker poll loop error")
            await asyncio.sleep(10)

    async def _expire_stale_approvals(self):
        """Expire pending approvals that have passed their expires_at."""
        try:
            expired = kernel.expire_stale_approvals()
            if expired:
                logger.info("Expired %d stale approval(s)", expired)
        except Exception:
            logger.exception("Failed to expire stale approvals")

    async def _smart_notification_check(self):
        """Check for stagnant goals and create notifications."""
        try:
            # Check for stagnant goals (no activity for 3+ days)
            stagnant_goals = kernel.query_state(
                "goals",
                status="active",
                last_activity_older_than_days=3,
                order="last_activity_asc",
                limit=5,
            )

            for goal in stagnant_goals:
                goal_id = goal.get("id", "")
                title = goal.get("title", "")
                last_activity = goal.get("last_activity_at") or goal.get("created_at", "")

                # Check if we already notified about this goal recently
                existing = kernel.query_state(
                    "notifications",
                    related_id=goal_id,
                    notification_type="goal_stagnant",
                    limit=1,
                )
                if existing:
                    # Check if notification was created after last activity
                    notif_time = existing[0].get("created_at", "")
                    if notif_time > last_activity:
                        continue  # Already notified after last activity

                # Calculate days stagnant
                try:
                    activity_dt = datetime.fromisoformat(last_activity)
                    days_stagnant = (datetime.now(UTC) - activity_dt).days
                except (ValueError, TypeError):
                    days_stagnant = 3

                # Create notification
                kernel.emit_event(
                    EVENT_NOTIFICATION_CREATED,
                    AGGREGATE_NOTIFICATION,
                    f"notif_stagnant_{goal_id}",
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

        except Exception:
            logger.exception("Failed smart notification check")

    async def _process_pending(self):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM background_tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchall()

        for row in rows:
            task = dict(row)
            await self._execute_background_task(task)

    async def _execute_background_task(self, task: dict):
        """Execute with self-healing: replan on repeated failure patterns."""
        from app.core.runtime.agent_bootstrap import ensure_agent

        task_id = task["id"]
        user_request = task.get("user_request", "")
        plan_json = task.get("plan_json", "{}")
        replan_count = 0

        while replan_count <= REPLAN_MAX_ATTEMPTS:
            kernel.emit_event(
                EVENT_BG_TASK_STATUS_CHANGED, AGGREGATE_BACKGROUND_TASK,
                f"bg_{task_id}",
                payload={"task_id": task_id, "status": "running",
                         "progress": 0.1 + replan_count * 0.3},
                actor="background",
            )

            await ensure_agent(kernel)
            from app.core.runtime.agent_scheduler import get_scheduler

            scheduler = get_scheduler(kernel)
            await scheduler.start()

            result = await kernel.submit_command(
                "BackgroundTaskRequested", AGGREGATE_BACKGROUND_TASK,
                f"bg_{task_id}",
                payload={"task_id": task_id, "plan_json": plan_json,
                         "replan_count": replan_count},
                actor="background", timeout=120.0,
            )

            # Check for failure and trigger self-healing
            if self._is_task_failed(result) and replan_count < REPLAN_MAX_ATTEMPTS:
                failing_tools = _critic.get_failing_tools(task_id)
                if failing_tools:
                    logger.warning("Self-healing: replanning task %s (attempt %d), failing tools=%s",
                                   task_id, replan_count + 1, failing_tools)
                    try:
                        from app.core.agents.planner import planner
                        prev_plan = json.loads(plan_json) if plan_json else {}
                        new_plan = await planner.replan(
                            user_request=user_request,
                            previous_plan=prev_plan,
                            failed_steps=[],
                            failing_tools=failing_tools,
                            failure_reason=f"Tools {failing_tools} failed repeatedly",
                        )
                        if new_plan.get("steps"):
                            plan_json = json.dumps(new_plan)
                            _critic.reset_for_task(task_id)
                            replan_count += 1
                            logger.info("Self-healing: new plan generated for task %s", task_id)
                            continue
                    except Exception:
                        logger.exception("Self-healing replan failed for task %s", task_id)
                break
            break

    @staticmethod
    def _is_task_failed(result: dict | None) -> bool:
        if not result:
            return True
        status = result.get("status", "")
        if status in ("failed", "error", "timeout"):
            return True
        return False

    def create_task(self, user_request: str, plan: dict | None = None) -> dict:
        task_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        plan_json = json.dumps(plan) if plan else None

        kernel.emit_event(
            EVENT_BG_TASK_CREATED,
            AGGREGATE_BACKGROUND_TASK,
            f"bg_{task_id}",
            payload={
                "task_id": task_id,
                "user_request": user_request,
                "plan_json": plan_json,
                "status": "pending",
                "progress": 0.0,
                "created_at": now,
            },
            actor="user",
        )

        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Background task {task_id} not found after creation")
        return task

    def get_task(self, task_id: str) -> dict | None:
        with db.get_db() as conn:
            row = conn.execute("SELECT * FROM background_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[dict]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM background_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


background_worker = BackgroundWorker()

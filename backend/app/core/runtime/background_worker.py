"""Background Worker — executes long-running background tasks via Kernel."""

import asyncio
import json
import uuid
from datetime import datetime

from app.core.runtime.kernel_instance import kernel
from app.store.database import db


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
                await self._process_pending()
            except Exception as e:
                print(f"Background worker error: {e}")
            await asyncio.sleep(10)

    async def _process_pending(self):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM background_tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchall()

        for row in rows:
            task = dict(row)
            await self._execute_background_task(task)

    async def _execute_background_task(self, task: dict):
        task_id = task["id"]
        self._update_status(task_id, "running", progress=0.1)

        try:
            plan = json.loads(task.get("plan_json", "{}")) if task.get("plan_json") else {"steps": []}
            steps = plan.get("steps", [])

            for i, step in enumerate(steps):
                tool_name = step.get("tool", "web_search")
                params = step.get("params", {"query": task["user_request"]})
                cap = await kernel.invoke_capability(
                    name=tool_name,
                    args=params,
                    actor="background",
                )
                if cap["status"] == "pending":
                    self._update_status(task_id, "waiting_approval", progress=0.1 + (0.8 * i / max(len(steps), 1)))
                    return

                progress = 0.1 + (0.8 * (i + 1) / max(len(steps), 1))
                self._update_status(task_id, "running", progress=progress)

            self._update_status(task_id, "completed", progress=1.0)
        except Exception:
            self._update_status(task_id, "failed", progress=0)

    def _update_status(self, task_id: str, status: str, progress: float = 0):
        now = datetime.utcnow().isoformat()
        completed_at = now if status in ("completed", "failed") else None
        with db.get_db() as conn:
            conn.execute(
                "UPDATE background_tasks SET status = ?, progress = ?, completed_at = ? WHERE id = ?",
                (status, progress, completed_at, task_id),
            )

    def create_task(self, user_request: str, plan: dict | None = None) -> dict:
        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO background_tasks (id, user_request, plan_json, status, progress, created_at)
                   VALUES (?, ?, ?, 'pending', 0, ?)""",
                (task_id, user_request, json.dumps(plan) if plan else None, now),
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

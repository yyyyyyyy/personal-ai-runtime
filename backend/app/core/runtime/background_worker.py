"""Background task lifecycle management — public API via Kernel.

v0.3.0: Polling and execution loop moved to RuntimeLoop.
This module retains only the public API: create_task / get_task / list_tasks.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from app.core.runtime.kernel.constants import (
    AGGREGATE_BACKGROUND_TASK,
    EVENT_BG_TASK_CREATED,
)
from app.core.runtime.kernel_instance import kernel

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Background task lifecycle management (public API only).

    v0.3.0: The polling loop and maintenance tasks are now driven by
    RuntimeLoop.  create_task / get_task / list_tasks remain as the
    public API.
    """

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
        rows = kernel.query_state("background_tasks", id=task_id)
        return rows[0] if rows else None

    def list_tasks(self, limit: int = 50) -> list[dict]:
        return kernel.query_state("background_tasks", limit=limit)


background_worker = BackgroundWorker()
# registered in RuntimeContainer.inventory()

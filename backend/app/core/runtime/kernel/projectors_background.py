"""Background task projectors — materialise background_tasks from event log (B1).

background_tasks remains APP_STORAGE (not GOVERNED); only Kernel projectors write
the table after emit_event.
"""

from __future__ import annotations

from .constants import (
    AGGREGATE_BACKGROUND_TASK,
    EVENT_BG_TASK_COMPLETED,
    EVENT_BG_TASK_CREATED,
    EVENT_BG_TASK_FAILED,
    EVENT_BG_TASK_STATUS_CHANGED,
)
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_BACKGROUND_TASK] = ["background_tasks"]


@projector(EVENT_BG_TASK_CREATED)
def _on_background_task_created(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    conn.execute(
        """INSERT OR REPLACE INTO background_tasks
           (id, user_request, plan_json, status, progress, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            p.get("user_request", ""),
            p.get("plan_json"),
            p.get("status", "pending"),
            float(p.get("progress", 0)),
            p.get("created_at", event.ts),
            p.get("completed_at"),
        ),
    )


@projector(EVENT_BG_TASK_STATUS_CHANGED)
def _on_background_task_status_changed(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    fields = ["status = ?", "progress = ?"]
    params: list[object] = [p.get("status", "pending"), float(p.get("progress", 0))]
    if "completed_at" in p:
        fields.append("completed_at = ?")
        params.append(p["completed_at"])
    params.append(task_id)
    conn.execute(
        f"UPDATE background_tasks SET {', '.join(fields)} WHERE id = ?",
        params,
    )


@projector(EVENT_BG_TASK_COMPLETED)
def _on_background_task_completed(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    status = p.get("status", "completed")
    progress = float(p.get("progress", 1.0 if status == "completed" else 0.1))
    completed_at = p.get("completed_at", event.ts if status == "completed" else None)
    conn.execute(
        """UPDATE background_tasks
           SET status = ?, progress = ?, completed_at = ?
           WHERE id = ?""",
        (status, progress, completed_at, task_id),
    )


@projector(EVENT_BG_TASK_FAILED)
def _on_background_task_failed(event: Event, conn) -> None:
    p = event.payload
    task_id = p.get("task_id") or event.aggregate_id.removeprefix("bg_")
    conn.execute(
        """UPDATE background_tasks
           SET status = 'failed', progress = ?, completed_at = ?
           WHERE id = ?""",
        (
            float(p.get("progress", 0)),
            p.get("completed_at", event.ts),
            task_id,
        ),
    )

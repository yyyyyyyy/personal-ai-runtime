"""ScheduledExecution persistence reader — Kernel-space scanner for handler_executions.

Read paths over the projection; writes happen exclusively through execution
projectors reacting to Execution* events. The Scheduler uses these scanners to
recover interrupted ScheduledExecutions after a restart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .query_builder import build_where, safe_order

if TYPE_CHECKING:
    from app.core.runtime.scheduled_execution import ScheduledExecution

STATUS_RUNNING = "running"
STATUS_PENDING = "pending"
STATUS_RETRYING = "retrying"
RECOVERABLE_STATUSES = (STATUS_PENDING, STATUS_RETRYING)

_ORDER_BY_CREATED_ASC = {"asc": "created_at ASC"}
_BASE_SELECT = "SELECT * FROM handler_executions"


def read_scheduled_execution(db: Any, execution_id: str) -> "ScheduledExecution | None":
    """Read one ScheduledExecution by id (O(1) projection lookup)."""
    from app.core.runtime.scheduled_execution import ScheduledExecution

    with db.get_db() as conn:
        row = conn.execute(
            f"{_BASE_SELECT} WHERE id = ?",
            (execution_id,),
        ).fetchone()
    if row is None:
        return None
    return ScheduledExecution.from_row(dict(row))


def read_scheduled_executions(
    db: Any,
    status: str | None = None,
    instance_id: str | None = None,
) -> list["ScheduledExecution"]:
    """Read ScheduledExecutions from the handler_executions projection."""
    from app.core.runtime.scheduled_execution import ScheduledExecution

    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if instance_id is not None:
        clauses.append("instance_id = ?")
        params.append(instance_id)
    where = build_where(clauses)
    order_sql = safe_order("asc", _ORDER_BY_CREATED_ASC, default_key="asc")
    with db.get_db() as conn:
        rows = conn.execute(
            f"{_BASE_SELECT}{where}{order_sql}",
            params,
        ).fetchall()
    return [ScheduledExecution.from_row(dict(r)) for r in rows]


def recover_scheduled_executions(
    db: Any,
) -> tuple[list["ScheduledExecution"], list["ScheduledExecution"]]:
    """Scan ScheduledExecutions needing recovery after a restart.

    Returns ``(running, pending)``. Performs NO writes.
    """
    from app.core.runtime.scheduled_execution import ScheduledExecution

    order_sql = safe_order("asc", _ORDER_BY_CREATED_ASC, default_key="asc")

    placeholders = ",".join("?" * len(RECOVERABLE_STATUSES))
    with db.get_db() as conn:
        running_rows = conn.execute(
            f"{_BASE_SELECT} WHERE status = ?{order_sql}",
            (STATUS_RUNNING,),
        ).fetchall()
        pending_rows = conn.execute(
            f"{_BASE_SELECT} WHERE status IN ({placeholders}){order_sql}",
            tuple(RECOVERABLE_STATUSES),
        ).fetchall()
    running = [ScheduledExecution.from_row(dict(r)) for r in running_rows]
    pending = [ScheduledExecution.from_row(dict(r)) for r in pending_rows]
    return running, pending


def count_scheduled_executions_by_status(db: Any) -> dict[str, int]:
    """Return ``{status: count}`` for all handler_executions rows."""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM handler_executions GROUP BY status"
        ).fetchall()
    return {str(r["status"]): int(r["c"]) for r in rows}

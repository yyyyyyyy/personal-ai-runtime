"""WorkItem persistence reader — Kernel-space scanner for handler_executions.

Lives under ``core/runtime/kernel`` so the ``SELECT FROM handler_executions``
statements stay inside Kernel Space (INV-4 boundary guard).

These are *read* paths over the projection; writes still happen exclusively
through the execution projectors reacting to Execution* events. The Scheduler
uses these scanners to recover interrupted WorkItems after a restart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .query_builder import build_where, safe_order

if TYPE_CHECKING:
    from app.core.runtime.work_item import WorkItem


# Status literals used as query constants. Defined here (not inlined in
# f-strings) so the projection's status vocabulary has exactly one source.
STATUS_RUNNING = "running"
STATUS_PENDING = "pending"
STATUS_RETRYING = "retrying"
RECOVERABLE_STATUSES = (STATUS_PENDING, STATUS_RETRYING)

_ORDER_BY_CREATED_ASC = {"asc": "created_at ASC"}
_BASE_SELECT = "SELECT * FROM handler_executions"


def read_work_items(
    db: Any,
    status: str | None = None,
    instance_id: str | None = None,
) -> list["WorkItem"]:
    """Read WorkItems from the handler_executions projection."""
    from app.core.runtime.work_item import WorkItem

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
    return [WorkItem.from_row(dict(r)) for r in rows]


def recover_work_items(db: Any) -> tuple[list["WorkItem"], list["WorkItem"]]:
    """Scan WorkItems needing recovery after a restart.

    Returns ``(running, pending)``. ``running`` items still have
    ``status='running'`` in the projection and MUST be transitioned by the
    caller (Scheduler._recover) via Execution* events before re-enqueue.
    This function performs NO writes.
    """
    from app.core.runtime.work_item import WorkItem

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
    running = [WorkItem.from_row(dict(r)) for r in running_rows]
    pending = [WorkItem.from_row(dict(r)) for r in pending_rows]
    return running, pending

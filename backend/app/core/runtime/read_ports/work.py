"""Work-item / goal ports — projections and Work mutations (API ABI).

Read helpers query governed ``work_items``. Mutation helpers are thin,
lazy wrappers over ``task_engine`` so API does not import that module
directly (avoids task_engine ↔ read_ports import cycles).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.runtime.read_ports._common import kernel

logger = logging.getLogger(__name__)


def query_pending_actions(*, limit: int = 5) -> list[dict[str, Any]]:
    """Query pending work items."""
    return kernel().query_state(
        "work_items",
        status="pending",
        limit=limit,
        order="created_at_asc",
    )


def query_top_active_goals(*, limit: int = 5) -> list[dict[str, Any]]:
    """Top active goals ordered by importance × urgency.

    Reads from work_items(work_type='goal').
    """
    return kernel().query_state(
        "work_items", work_type="goal",
        status_in=("active", "in_progress"),
        limit=limit,
        order="importance_urgency_desc",
    )


def query_stagnant_goals(*, days: int = 3, limit: int = 10) -> list[dict[str, Any]]:
    """Active goals with no recent activity (Work subtype work_type=goal)."""
    return kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        last_activity_older_than_days=days,
        limit=limit,
    )


def query_stagnant_goal_count(*, days: int = 3) -> int:
    """Count active goals with no recent activity."""
    try:
        return kernel().count_state(
            "work_items",
            work_type="goal",
            status="active",
            last_activity_older_than_days=days,
        )
    except Exception:
        logger.exception("query_stagnant_goal_count failed")
        raise


def query_work_item(item_id: str) -> dict[str, Any] | None:
    """Fetch a single work_items row by id."""
    rows = kernel().query_state("work_items", id=item_id, limit=1)
    return rows[0] if rows else None


def query_work_items(**filters: Any) -> list[dict[str, Any]]:
    """Pass-through work_items query — prefer more specific helpers when possible."""
    return kernel().query_state("work_items", **filters)


def query_goals(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List goals (work_type=goal)."""
    filters: dict[str, Any] = {"work_type": "goal", "limit": limit}
    if status:
        filters["status"] = status
    return kernel().query_state("work_items", **filters)


def count_goals(*, status: str | None = None) -> int:
    """Count goals."""
    filters: dict[str, Any] = {"work_type": "goal"}
    if status:
        filters["status"] = status
    return kernel().count_state("work_items", **filters)


def query_goal(goal_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("work_items", work_type="goal", id=goal_id, limit=1)
    return rows[0] if rows else None


def query_goal_actions(goal_id: str) -> list[dict[str, Any]]:
    """Child actions of a goal."""
    return kernel().query_state(
        "work_items", parent_goal_id=goal_id, work_type="action",
    )


def query_work_items_by_parent_goal(
    goal_id: str,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    return kernel().query_state("work_items", parent_goal_id=goal_id, limit=limit)


def query_active_goals(
    *,
    limit: int = 20,
    order: str = "importance_desc",
) -> list[dict[str, Any]]:
    return kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        limit=limit,
        order=order,
    )


def count_active_goals() -> int:
    return kernel().count_state(
        "work_items",
        work_type="goal",
        status="active",
    )


def query_completed_goals(
    *,
    limit: int = 5000,
    updated_since: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {
        "work_type": "goal",
        "status": "completed",
        "limit": limit,
    }
    if updated_since:
        filters["updated_since"] = updated_since
    return kernel().query_state("work_items", **filters)


def count_completed_goals(
    *,
    updated_since: str | None = None,
) -> int:
    filters: dict[str, Any] = {
        "work_type": "goal",
        "status": "completed",
    }
    if updated_since:
        filters["updated_since"] = updated_since
    return kernel().count_state("work_items", **filters)


def query_goals_with_deadline(*, limit: int = 500) -> list[dict[str, Any]]:
    """Active goals that have a deadline set."""
    return kernel().query_state(
        "work_items",
        work_type="goal",
        status="active",
        has_deadline=True,
        limit=limit,
    )


def query_pending_work_items(*, limit: int = 100) -> list[dict[str, Any]]:
    return kernel().query_state("work_items", status="pending", limit=limit)


# ── Work mutations (API-facing ABI; lazy to avoid task_engine ↔ read_ports cycles)


def create_work_item(
    title: str,
    *,
    description: str = "",
    work_type: str = "task",
    parent_goal_id: str | None = None,
    parent_work_id: str | None = None,
    priority: int = 0,
    dependencies: list[str] | None = None,
    executable_plan: str | None = None,
    progress: float | None = None,
    importance: float | None = None,
    urgency: float | None = None,
    deadline: str | None = None,
    last_activity_at: str | None = None,
    status: str = "pending",
) -> dict[str, Any]:
    from app.core.runtime.task_engine import create_work_item as _create

    return _create(
        title,
        description=description,
        work_type=work_type,
        parent_goal_id=parent_goal_id,
        parent_work_id=parent_work_id,
        priority=priority,
        dependencies=dependencies,
        executable_plan=executable_plan,
        progress=progress,
        importance=importance,
        urgency=urgency,
        deadline=deadline,
        last_activity_at=last_activity_at,
        status=status,
    )


def update_work_item_fields(
    item_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    progress: float | None = None,
    importance: float | None = None,
    urgency: float | None = None,
    deadline: str | None = None,
    last_activity_at: str | None = None,
    parent_work_id: str | None = None,
) -> dict[str, Any] | None:
    from app.core.runtime.task_engine import update_work_item_fields as _update

    return _update(
        item_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        progress=progress,
        importance=importance,
        urgency=urgency,
        deadline=deadline,
        last_activity_at=last_activity_at,
        parent_work_id=parent_work_id,
    )


def update_work_item_status(item_id: str, new_status: str) -> dict[str, Any] | None:
    from app.core.runtime.task_engine import update_work_item_status as _update

    return _update(item_id, new_status)


def delete_work_item(item_id: str, *, cascade: bool = False) -> None:
    from app.core.runtime.task_engine import delete_work_item as _delete

    _delete(item_id, cascade=cascade)


def get_work_item(item_id: str) -> dict[str, Any] | None:
    """Alias of ``query_work_item`` — kept for Work API call sites."""
    return query_work_item(item_id)


def get_sub_work_items(parent_work_id: str) -> list[dict[str, Any]]:
    from app.core.runtime.task_engine import get_sub_work_items as _get

    return _get(parent_work_id)


def get_work_item_tree(goal_id: str) -> list[dict[str, Any]]:
    from app.core.runtime.task_engine import get_work_item_tree as _get

    return _get(goal_id)


def list_work_items(
    status: str | None = None,
    work_type: str | None = None,
    limit: int = 50,
    parent_work_id: str | None = None,
    parent_goal_id: str | None = None,
) -> list[dict[str, Any]]:
    from app.core.runtime.task_engine import list_work_items as _list

    return _list(
        status=status,
        work_type=work_type,
        limit=limit,
        parent_work_id=parent_work_id,
        parent_goal_id=parent_goal_id,
    )


def bump_parent_activity(parent_id: str) -> None:
    from app.core.runtime.task_engine import bump_parent_activity as _bump

    _bump(parent_id)


def notify_goal_action_completed(
    goal_id: str,
    action_id: str,
    action_title: str,
) -> None:
    """Notify + memory side-effects when a goal's child action completes.

    Shared by the Work API status transitions and ExecuteRequested completion
    so plan execution does not skip product side-effects.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        all_items = query_work_items_by_parent_goal(goal_id, limit=500)

        # Ensure the just-completed action is counted even if a concurrent
        # read races the projector (emit is sync, but belt-and-suspenders).
        for item in all_items:
            if item["id"] == action_id:
                item["status"] = "completed"

        completed = (
            sum(1 for a in all_items if a.get("status") == "completed")
            if all_items
            else 0
        )

        goal_row = query_goal(goal_id)
        goal_title = goal_row["title"] if goal_row else "目标"
        all_done = bool(all_items) and all(
            a.get("status") == "completed" for a in all_items
        )
        if all_done:
            from app.core.runtime.read_ports.notifications import create_notification

            create_notification(
                "goal_complete",
                f"目标「{goal_title}」的所有步骤已完成",
                f"你完成了所有行动步骤：{goal_title}。可以去目标页标记完成，或让 AI 帮你总结经验。",
            )
        else:
            from app.core.runtime.read_ports.notifications import create_notification

            total = len(all_items) if all_items else 0
            create_notification(
                "goal_progress",
                f"完成一步：{action_title}",
                f"目标「{goal_title}」进度：{completed}/{total} 步已完成。",
            )

        from app.core.agents.memory_engine import memory_engine

        memory_engine.store_memory(
            category="event",
            content=f"完成了行动步骤：{action_title}（目标：{goal_title}）",
            source=f"action:{action_id}",
            actor="system",
        )
    except Exception:
        logger.warning(
            "Failed to store audited action memory for action_id=%s",
            action_id,
            exc_info=True,
        )


_TERMINAL_EXECUTE_STATUSES = frozenset({"completed", "cancelled"})
_BLOCKED_EXECUTE_STATUSES = frozenset({"running", "waiting_approval"})


def request_work_item_execute(item_id: str) -> dict[str, Any]:
    """Start a work item's ``executable_plan`` (Ports command ABI).

    Emits ``WorkItemStatusChanged(running)`` then ``ExecuteRequested``.
    The Scheduler dispatches the handler asynchronously; completion updates
    the work-item status via ``WorkItemStatusChanged`` from the handler.
    """
    import json

    from app.core.runtime.kernel.constants import (
        AGGREGATE_WORK_ITEM,
        EVENT_EXECUTE_REQUESTED,
        EVENT_WORK_ITEM_STATUS_CHANGED,
    )

    item = query_work_item(item_id)
    if item is None:
        raise KeyError(item_id)

    if item.get("work_type") == "goal":
        raise ValueError("Goals cannot be executed; run child actions instead")

    plan_raw = item.get("executable_plan")
    if not isinstance(plan_raw, str) or not plan_raw.strip():
        raise ValueError("Work item has no executable_plan")
    try:
        plan_obj = json.loads(plan_raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid executable_plan JSON: {exc}") from exc
    if not isinstance(plan_obj, dict) or not isinstance(plan_obj.get("steps"), list):
        raise ValueError("executable_plan must be an object with a steps list")
    if not any(isinstance(s, dict) for s in plan_obj["steps"]):
        raise ValueError("executable_plan has no steps")

    status = item.get("status") or "pending"
    if status in _TERMINAL_EXECUTE_STATUSES:
        raise ValueError(f"Work item already terminal ({status})")
    if status in _BLOCKED_EXECUTE_STATUSES:
        raise ValueError(
            f"Work item is {status}; wait for completion or resolve approval"
        )

    k = kernel()
    k.emit_event(
        EVENT_WORK_ITEM_STATUS_CHANGED,
        AGGREGATE_WORK_ITEM,
        item_id,
        payload={"status": "running"},
        actor="user",
    )
    k.emit_event(
        EVENT_EXECUTE_REQUESTED,
        "action",
        f"exec_{item_id}",
        payload={"action_id": item_id},
        actor="user",
    )

    updated = query_work_item(item_id)
    if updated is None:
        raise RuntimeError("Work item missing after execute request")
    return updated


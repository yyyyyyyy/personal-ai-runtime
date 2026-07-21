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


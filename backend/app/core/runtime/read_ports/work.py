"""Work-item / goal projection read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


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
        return 0


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


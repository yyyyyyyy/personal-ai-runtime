"""Timer, policy, and background-task read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import db, kernel, qb


def query_background_task(task_id: str) -> dict[str, Any] | None:
    rows = qb().query_background_tasks(db(), {"id": task_id, "limit": 1})
    return rows[0] if rows else None


def query_background_tasks(
    *,
    status: str | None = None,
    limit: int = 50,
    order: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if status:
        filters["status"] = status
    if order:
        filters["order"] = order
    return qb().query_background_tasks(db(), filters)


def query_active_timers(*, limit: int = 100) -> list[dict[str, Any]]:
    return qb().query_timer_events(db(), {"status": "active", "limit": limit})


def query_timer(timer_id: str) -> dict[str, Any] | None:
    rows = qb().query_timer_events(db(), {"id": timer_id, "limit": 1})
    return rows[0] if rows else None


def query_due_timers(*, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
    """Active timers whose fire_at is at or before now_iso."""
    return qb().query_timer_events(
        db(),
        {"status": "active", "fire_at_lt": now_iso, "limit": limit},
    )


def query_active_policies(*, limit: int = 200) -> list[dict[str, Any]]:
    return kernel().query_state("policy_events", status="active", limit=limit)


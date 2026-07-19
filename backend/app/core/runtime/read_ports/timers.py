"""Timer, policy, and background-task read ports."""

from __future__ import annotations

import logging
from typing import Any

from app.core.runtime.read_ports._common import kernel

logger = logging.getLogger(__name__)


def query_background_task(task_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("background_tasks", id=task_id, limit=1)
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
    return kernel().query_state("background_tasks", **filters)


def query_active_timers(*, limit: int = 100) -> list[dict[str, Any]]:
    return kernel().query_state("timer_events", status="active", limit=limit)


def count_active_timers() -> int:
    """Exact active timer COUNT (not capped by list LIMIT)."""
    try:
        return kernel().count_state("timer_events", status="active")
    except Exception:
        logger.exception("count_active_timers failed")
        raise


def query_timer(timer_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("timer_events", id=timer_id, limit=1)
    return rows[0] if rows else None


def query_due_timers(*, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
    """Active timers whose fire_at is at or before now_iso."""
    return kernel().query_state(
        "timer_events",
        status="active",
        fire_at_lt=now_iso,
        limit=limit,
    )


def query_active_policies(*, limit: int = 200) -> list[dict[str, Any]]:
    return kernel().query_state("policy_events", status="active", limit=limit)


def count_active_policies() -> int:
    """Exact active policy COUNT (not capped by list LIMIT)."""
    try:
        return kernel().count_state("policy_events", status="active")
    except Exception:
        logger.exception("count_active_policies failed")
        raise

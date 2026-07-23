"""Timer, policy, background-task reads, and Triggers registration ABI.

Trigger helpers live here because reactions participate in the periodic
RuntimeLoop cycle alongside timers — not because they are timer rows.
"""

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


def cancel_background_task(task_id: str) -> dict[str, Any]:
    """Cancel a non-terminal background task (Ports command ABI).

    Emits ``BackgroundTaskCompleted(status=cancelled)``, requests cooperative
    cancel for in-flight plan steps, and cancels matching Lane A handlers when
    the Scheduler is alive.

    The in-process cancel flag is **not** cleared here — the handler clears it
    after acknowledging cancel, so a long ``invoke_capability`` cannot race
    past a cleared flag and overwrite ``cancelled`` with ``completed``.
    """
    from app.core.runtime.execution import request_cancel_background_task
    from app.core.runtime.kernel.constants import (
        AGGREGATE_BACKGROUND_TASK,
        EVENT_BG_TASK_COMPLETED,
    )
    from app.core.runtime.plan_resume import clear_plan_resumes_for_background_task

    task = query_background_task(task_id)
    if task is None:
        raise KeyError(task_id)

    status = task.get("status") or ""
    if status in ("completed", "failed", "cancelled"):
        raise ValueError(f"Task already terminal ({status})")

    request_cancel_background_task(task_id)

    try:
        from app.core.runtime.agent_scheduler import get_scheduler
        from app.core.runtime.runtime_container import runtime

        if runtime._scheduler is not None:
            get_scheduler(kernel()).cancel_background_task_executions(task_id)
    except Exception:
        logger.debug("Scheduler cancel for background task skipped", exc_info=True)

    # Always clear by task_id — projection has no approval_id column.
    clear_plan_resumes_for_background_task(task_id, kernel=kernel())

    kernel().emit_event(
        EVENT_BG_TASK_COMPLETED,
        AGGREGATE_BACKGROUND_TASK,
        f"bg_{task_id}",
        payload={
            "task_id": task_id,
            "status": "cancelled",
            "progress": float(task.get("progress") or 0),
        },
        actor="user",
    )

    updated = query_background_task(task_id)
    if updated is None:
        raise RuntimeError("Task missing after cancel")
    return updated


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


# ── Trigger / reaction registration (API-facing ABI)


def register_trigger_reaction(
    *,
    name: str,
    every_cycle: bool = True,
    event_types: list[str] | None = None,
    aggregate_type: str = "",
    count_gte: int = 0,
    window_days: int = 1,
    state_selector: str = "",
    state_filters: dict[str, Any] | None = None,
    notification_template: str = "",
) -> dict[str, Any]:
    """Register a metadata-only reaction for the Triggers API."""
    from app.core.runtime.reaction_registry import (
        Reaction,
        ReactionThen,
        ReactionWhen,
        get_reaction_registry,
    )

    when = ReactionWhen(
        every_cycle=every_cycle,
        event_types=list(event_types or []),
        aggregate_type=aggregate_type,
        count_gte=count_gte,
        window_days=window_days,
        state_selector=state_selector,
        state_filters=dict(state_filters or {}),
    )
    then = ReactionThen(notification_template=notification_template)
    get_reaction_registry().register(Reaction(name=name, when=when, then=then))
    return {
        "name": name,
        "status": "registered",
        "note": "without a handler this reaction will not fire in evaluate_cycle",
    }


def list_trigger_reactions() -> list[dict[str, Any]]:
    from app.core.runtime.reaction_registry import get_reaction_registry

    return get_reaction_registry().list_reactions()


def unregister_trigger_reaction(name: str) -> bool:
    from app.core.runtime.reaction_registry import get_reaction_registry

    return get_reaction_registry().unregister(name)


def count_state_selectors() -> frozenset[str]:
    """Selectors accepted by ``kernel.count_state`` / trigger count gates."""
    from app.core.runtime.kernel.kernel_query_state import COUNT_STATE_SELECTORS

    return COUNT_STATE_SELECTORS

"""Friction log — dogfood feedback captured as immutable events.

Friction points live only in event_log (no projection table). Use during
daily self-use: log what felt bad, resolve when fixed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.runtime.kernel.constants import (
    AGGREGATE_FRICTION,
    EVENT_FRICTION_LOGGED,
    EVENT_FRICTION_RESOLVED,
)
from app.core.runtime.kernel_instance import kernel

VALID_AREAS = frozenset({"chat", "inbox", "goals", "memory", "tools", "setup", "other"})
VALID_SEVERITIES = frozenset({"low", "medium", "high"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _replay_friction(events: list) -> dict[str, dict[str, Any]]:
    """Build friction state from FrictionLogged / FrictionResolved events."""
    items: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.type == EVENT_FRICTION_LOGGED:
            p = event.payload or {}
            items[event.aggregate_id] = {
                "id": event.aggregate_id,
                "note": p.get("note", ""),
                "area": p.get("area", "other"),
                "severity": p.get("severity", "medium"),
                "status": "open",
                "created_at": p.get("created_at", event.ts),
                "resolved_at": None,
            }
        elif event.type == EVENT_FRICTION_RESOLVED:
            if event.aggregate_id in items:
                p = event.payload or {}
                items[event.aggregate_id]["status"] = "resolved"
                items[event.aggregate_id]["resolved_at"] = p.get(
                    "resolved_at", event.ts
                )
    return items


def log_friction(
    note: str,
    *,
    area: str = "other",
    severity: str = "medium",
) -> dict[str, Any]:
    """Record a friction point. Returns the created entry."""
    note = note.strip()
    if not note:
        raise ValueError("note must not be empty")
    if area not in VALID_AREAS:
        raise ValueError(f"area must be one of {sorted(VALID_AREAS)}")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")

    friction_id = f"fric_{uuid.uuid4().hex[:12]}"
    now = _now()
    kernel.emit_event(
        EVENT_FRICTION_LOGGED,
        AGGREGATE_FRICTION,
        friction_id,
        payload={
            "note": note,
            "area": area,
            "severity": severity,
            "created_at": now,
        },
        actor="user",
    )
    return {
        "id": friction_id,
        "note": note,
        "area": area,
        "severity": severity,
        "status": "open",
        "created_at": now,
        "resolved_at": None,
    }


def resolve_friction(friction_id: str) -> dict[str, Any] | None:
    """Mark a friction point resolved. Returns updated entry or None if missing."""
    events = kernel.read_events(
        aggregate_type=AGGREGATE_FRICTION,
        aggregate_id=friction_id,
    )
    if not events:
        return None

    state = _replay_friction(events)
    entry = state.get(friction_id)
    if not entry or entry["status"] == "resolved":
        return entry

    now = _now()
    kernel.emit_event(
        EVENT_FRICTION_RESOLVED,
        AGGREGATE_FRICTION,
        friction_id,
        payload={"resolved_at": now},
        actor="user",
    )
    entry["status"] = "resolved"
    entry["resolved_at"] = now
    return entry


def list_friction(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List friction points, newest first."""
    events = kernel.read_events(
        aggregate_type=AGGREGATE_FRICTION,
        types=[EVENT_FRICTION_LOGGED, EVENT_FRICTION_RESOLVED],
        order="asc",
    )
    items = _replay_friction(events)
    rows = sorted(
        items.values(),
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )
    if status:
        rows = [r for r in rows if r["status"] == status]
    return rows[:limit]


def friction_stats(*, since_days: int = 7) -> dict[str, Any]:
    """Aggregate friction stats for validation metrics."""
    since = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
    logged = kernel.read_events(
        type=EVENT_FRICTION_LOGGED,
        since_ts=since,
    )
    resolved = kernel.read_events(
        type=EVENT_FRICTION_RESOLVED,
        since_ts=since,
    )

    by_area: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for event in logged:
        p = event.payload or {}
        area = p.get("area", "other")
        severity = p.get("severity", "medium")
        by_area[area] = by_area.get(area, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    all_events = kernel.read_events(
        aggregate_type=AGGREGATE_FRICTION,
        types=[EVENT_FRICTION_LOGGED, EVENT_FRICTION_RESOLVED],
        order="asc",
    )
    all_items = _replay_friction(all_events)
    open_count = sum(1 for r in all_items.values() if r["status"] == "open")

    return {
        "logged_7d": len(logged),
        "resolved_7d": len(resolved),
        "open_total": open_count,
        "by_area_7d": by_area,
        "by_severity_7d": by_severity,
    }

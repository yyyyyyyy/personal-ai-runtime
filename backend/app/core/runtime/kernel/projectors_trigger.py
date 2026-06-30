"""Projectors for trigger — event-sourced write path for triggers table."""

import json

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["trigger"] = ["triggers"]


@projector("TriggerCreated")
def _on_trigger_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT INTO triggers
           (id, name, trigger_type, condition_json, action_type, action_config, enabled, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
        (
            event.aggregate_id,
            p.get("name", ""),
            p.get("trigger_type", ""),
            json.dumps(p.get("condition", {})),
            p.get("action_type", ""),
            json.dumps(p.get("action_config", {})) if p.get("action_config") else None,
            event.ts,
        ),
    )


@projector("TriggerDeleted")
def _on_trigger_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM triggers WHERE id = ?", (event.aggregate_id,))

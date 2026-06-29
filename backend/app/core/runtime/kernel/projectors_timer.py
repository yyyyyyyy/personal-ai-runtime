"""Timer projectors — materialise timer_events from Timer aggregate events.

timer_events is a projection of the Timer aggregate event stream.
TimerCreated is the sole aggregate creation event.
"""

from __future__ import annotations

from .constants import AGGREGATE_TIMER
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_TIMER] = ["timer_events"]

TIMER_DDL = """
CREATE TABLE IF NOT EXISTS timer_events (
    id               TEXT PRIMARY KEY,
    handler_name     TEXT NOT NULL,
    schedule_type    TEXT NOT NULL DEFAULT 'cron',
    cron_expr        TEXT NOT NULL DEFAULT '',
    delay_seconds    REAL NOT NULL DEFAULT 0,
    fire_at          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active',
    created_at       TEXT NOT NULL,
    fired_at         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_timer_events_status
    ON timer_events (status, fire_at);
"""


@projector("TimerCreated")
def _on_timer_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO timer_events
           (id, handler_name, schedule_type, cron_expr, delay_seconds, fire_at,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
        (
            event.aggregate_id,
            p.get("handler_name", ""),
            p.get("schedule_type", "cron"),
            p.get("cron_expr", ""),
            float(p.get("delay_seconds", 0)),
            p.get("fire_at", ""),
            event.ts,
        ),
    )


@projector("TimerFired")
def _on_timer_fired(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE timer_events SET status = 'fired', fired_at = ? WHERE id = ?",
        (p.get("fired_at", event.ts), event.aggregate_id),
    )


@projector("TimerCancelled")
def _on_timer_cancelled(event: Event, conn) -> None:
    conn.execute(
        "UPDATE timer_events SET status = 'cancelled' WHERE id = ?",
        (event.aggregate_id,),
    )

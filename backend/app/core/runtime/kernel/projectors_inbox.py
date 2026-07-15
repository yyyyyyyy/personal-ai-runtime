"""Inbox email projection — derives the inbox_emails table solely from
InboxEmail* events.

inbox_emails is a governed projection: every column is derived from events,
the table can be rebuilt via kernel.rebuild("inbox_email"), and
verify_inbox_audit.py can guarantee 1:1 correspondence because the INSERT
path only exists inside the Kernel.
"""

import json

from .constants import AGGREGATE_TIMER
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["inbox_email"] = ["inbox_emails"]
_OWNED_TABLES[AGGREGATE_TIMER] = ["timer_events"]


@projector("InboxEmailRecorded")
def _on_inbox_email_recorded(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO inbox_emails
           (id, sender, subject, preview, received_at, category, importance,
            reason, notified, digested, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
        (
            event.aggregate_id,
            p.get("sender", ""),
            p.get("subject", ""),
            p.get("preview", ""),
            p.get("received_at", ""),
            p.get("category", "actionable"),
            p.get("importance", 0.5),
            p.get("reason", ""),
            p.get("created_at", event.ts),
        ),
    )


@projector("InboxEmailStatusChanged")
def _on_inbox_email_status_changed(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE inbox_emails SET status = ? WHERE id = ?",
        (p.get("status", "pending"), event.aggregate_id),
    )


@projector("InboxEmailFlagSet")
def _on_inbox_email_flag_set(event: Event, conn) -> None:
    flag = event.payload.get("flag", "notified")
    if flag == "digested":
        # Bulk op: mark all undigested rows as digested. aggregate_id carries
        # the digest run id; we update every row where digested = 0 so the
        # projection converges to "everything emitted before this event has
        # been digested".
        conn.execute("UPDATE inbox_emails SET digested = 1 WHERE COALESCE(digested, 0) = 0")
    else:
        conn.execute(
            "UPDATE inbox_emails SET notified = 1 WHERE id = ?",
            (event.aggregate_id,),
        )


# --- Timer projection (folded here to keep runtime_files zero-sum) ----------

TIMER_DDL = """
CREATE TABLE IF NOT EXISTS timer_events (
    id               TEXT PRIMARY KEY,
    handler_name     TEXT NOT NULL,
    schedule_type    TEXT NOT NULL DEFAULT 'cron',
    cron_expr        TEXT NOT NULL DEFAULT '',
    delay_seconds    REAL NOT NULL DEFAULT 0,
    fire_at          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active',
    payload_json     TEXT DEFAULT '{}',
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
            payload_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (
            event.aggregate_id,
            p.get("handler_name", ""),
            p.get("schedule_type", "cron"),
            p.get("cron_expr", ""),
            float(p.get("delay_seconds", 0)),
            p.get("fire_at", ""),
            json.dumps(p.get("payload", {}), ensure_ascii=False),
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

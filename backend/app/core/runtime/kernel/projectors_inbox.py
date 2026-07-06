"""Inbox email projection — derives the inbox_emails table solely from
InboxEmail* events.

v0.3.0: closes Critical #1 from ARCHITECTURE_SURVIVAL_REVIEW.md. Previously
inbox_emails was written directly by app/product/inbox.py while InboxEmailRecorded
was emitted in parallel — a classic dual-write that could drift. The table is
now a governed projection: every column is derived from events, the table can
be rebuilt via kernel.rebuild("inbox_email"), and verify_inbox_audit.py can
guarantee 1:1 correspondence because the INSERT path no longer exists outside
the Kernel.
"""

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["inbox_email"] = ["inbox_emails"]


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


@projector("InboxEmailNotified")
def _on_inbox_email_notified(event: Event, conn) -> None:
    conn.execute(
        "UPDATE inbox_emails SET notified = 1 WHERE id = ?",
        (event.aggregate_id,),
    )


@projector("InboxEmailDigested")
def _on_inbox_email_digested(event: Event, conn) -> None:
    # Bulk op: mark all undigested rows as digested. aggregate_id carries the
    # digest run id; we update every row where digested = 0 so the projection
    # converges to "everything emitted before this event has been digested".
    conn.execute("UPDATE inbox_emails SET digested = 1 WHERE COALESCE(digested, 0) = 0")

"""Governance projectors — Policy + Grant event-sourced projections.

policy_events and grant_events are projections of Policy/Grant aggregate event
streams. Each is fully reconstructible from the Event Log.

This replaces capability_policy.json as the Governance Runtime Root of Trust.
"""

from __future__ import annotations

from .constants import AGGREGATE_GRANT, AGGREGATE_POLICY
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_POLICY] = ["policy_events"]

POLICY_DDL = """
CREATE TABLE IF NOT EXISTS policy_events (
    id               TEXT PRIMARY KEY,
    capability       TEXT NOT NULL,
    risk_level       TEXT NOT NULL DEFAULT 'low',  -- low | high | forbidden
    status           TEXT NOT NULL DEFAULT 'active',  -- active | revoked
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_events_capability
    ON policy_events (capability);
CREATE INDEX IF NOT EXISTS idx_policy_events_status
    ON policy_events (status);
"""

_OWNED_TABLES[AGGREGATE_GRANT] = ["grant_events"]

GRANT_DDL = """
CREATE TABLE IF NOT EXISTS grant_events (
    id               TEXT PRIMARY KEY,
    principal_id     TEXT NOT NULL,
    capability       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',  -- active | revoked
    created_at       TEXT NOT NULL,
    revoked_at       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_grant_events_principal
    ON grant_events (principal_id);
CREATE INDEX IF NOT EXISTS idx_grant_events_capability
    ON grant_events (principal_id, capability);
"""


# ── Policy projectors ───────────────────────────────────────────────────

@projector("PolicyCreated")
def _on_policy_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO policy_events
           (id, capability, risk_level, status, created_at, updated_at)
           VALUES (?, ?, ?, 'active', ?, ?)""",
        (
            event.aggregate_id,
            p.get("capability", ""),
            p.get("risk_level", "low"),
            event.ts,
            event.ts,
        ),
    )


@projector("PolicyUpdated")
def _on_policy_updated(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE policy_events SET risk_level = ?, updated_at = ? WHERE id = ?",
        (p.get("risk_level", "low"), event.ts, event.aggregate_id),
    )


@projector("PolicyRevoked")
def _on_policy_revoked(event: Event, conn) -> None:
    conn.execute(
        "UPDATE policy_events SET status = 'revoked', updated_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )

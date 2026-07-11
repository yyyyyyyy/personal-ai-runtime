"""Governance projectors — Policy event-sourced projections.

policy_events is a projection of Policy aggregate event streams, fully
reconstructible from the Event Log. Grant projections were removed in v0.9.0
(Gate 2 eliminated; no Grant* projectors remain).
"""

from __future__ import annotations

from .constants import AGGREGATE_POLICY
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


def _invalidate_risk_cache() -> None:
    """Policy table changed — drop CapabilityGovernance risk cache."""
    try:
        from app.core.runtime.capability_governance import capability_governance

        capability_governance.invalidate_risk_cache()
    except Exception:
        pass


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
    _invalidate_risk_cache()


@projector("PolicyUpdated")
def _on_policy_updated(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        "UPDATE policy_events SET risk_level = ?, updated_at = ? WHERE id = ?",
        (p.get("risk_level", "low"), event.ts, event.aggregate_id),
    )
    _invalidate_risk_cache()


@projector("PolicyRevoked")
def _on_policy_revoked(event: Event, conn) -> None:
    conn.execute(
        "UPDATE policy_events SET status = 'revoked', updated_at = ? WHERE id = ?",
        (event.ts, event.aggregate_id),
    )
    _invalidate_risk_cache()

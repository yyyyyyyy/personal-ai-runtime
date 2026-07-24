"""Governance projectors — Policy event-sourced projections.

policy_events is a projection of Policy aggregate event streams, fully
reconstructible from the Event Log.
"""

from __future__ import annotations

from .constants import AGGREGATE_POLICY
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES[AGGREGATE_POLICY] = ["policy_events"]


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
    status = p.get("status")
    if status == "revoked":
        conn.execute(
            "UPDATE policy_events SET status = 'revoked', updated_at = ? WHERE id = ?",
            (event.ts, event.aggregate_id),
        )
        _invalidate_risk_cache()
        return
    if status == "active":
        # Reactivation after intentional revoke (INV-C6): restore active + risk.
        risk = p.get("risk_level", "low")
        conn.execute(
            "UPDATE policy_events SET status = 'active', risk_level = ?, "
            "updated_at = ? WHERE id = ?",
            (risk, event.ts, event.aggregate_id),
        )
        _invalidate_risk_cache()
        return
    conn.execute(
        "UPDATE policy_events SET risk_level = ?, updated_at = ? WHERE id = ?",
        (p.get("risk_level", "low"), event.ts, event.aggregate_id),
    )
    _invalidate_risk_cache()


# --- Telemetry projections (folded to keep runtime_files zero-sum) ---

_OWNED_TABLES["capability"] = ["tool_calls"]
_OWNED_TABLES["llm_call"] = ["llm_calls"]


# ── tool_calls ────────────────────────────────────────────────────────────

@projector("CapabilityInvoked")
def _on_capability_invoked(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO tool_calls
           (id, tool_name, success, latency_ms, error_message, created_at)
           VALUES (?, ?, 1, ?, NULL, ?)""",
        (
            f"tc_{event.seq}",
            p.get("name", ""),
            p.get("latency_ms", 0),
            event.ts,
        ),
    )


@projector("CapabilityFailed")
def _on_capability_failed(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO tool_calls
           (id, tool_name, success, latency_ms, error_message, created_at)
           VALUES (?, ?, 0, ?, ?, ?)""",
        (
            f"tc_{event.seq}",
            p.get("name", ""),
            p.get("latency_ms", 0),
            p.get("error", ""),
            event.ts,
        ),
    )


@projector("CapabilityDenied")
def _on_capability_denied(event: Event, conn) -> None:
    """Denied calls are also tool calls (rejected before invocation)."""
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO tool_calls
           (id, tool_name, success, latency_ms, error_message, created_at)
           VALUES (?, ?, 0, 0, ?, ?)""",
        (
            f"tc_{event.seq}",
            p.get("name", ""),
            f"denied: {p.get('reason', '')}",
            event.ts,
        ),
    )


# ── llm_calls ─────────────────────────────────────────────────────────────

@projector("LLMCallRecorded")
def _on_llm_call_recorded(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO llm_calls
           (id, provider, model, prompt_tokens, completion_tokens,
            latency_ms, cost, success, error_message, purpose, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"llm_{event.seq}",
            p.get("provider", ""),
            p.get("model", ""),
            p.get("prompt_tokens", 0),
            p.get("completion_tokens", 0),
            p.get("latency_ms", 0),
            p.get("cost", 0),
            1 if p.get("success", True) else 0,
            p.get("error_message"),
            p.get("purpose") or "chat",
            event.ts,
        ),
    )

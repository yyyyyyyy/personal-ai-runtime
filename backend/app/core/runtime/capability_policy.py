"""Capability Policy — event-sourced governance.

Reads policy_events projection (from PolicyCreated/Updated/Revoked events)
instead of the static capability_policy.json. The JSON file is now just a
seed source — PolicyCreated events are emitted at startup, then the
projection becomes the authoritative root of trust.

External MCP tools (dynamically discovered) are now also event-sourced:
register_external_tool emits PolicyCreated/PolicyUpdated, and
clear_external_tools emits PolicyRevoked. The in-memory sets remain
as a fast-path cache synchronized with the event-sourced projection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class CapabilityPolicy:
    def __init__(self):
        self._external_auto_allow: set[str] = set()
        self._external_needs_user: set[str] = set()
        self._external_forbidden: set[str] = set()
        self._kernel = None  # Set during seed_from_json

    # ── Seed (startup) ────────────────────────────────────────────────

    def seed_from_json(self, kernel) -> None:
        """Emit PolicyCreated events from capability_policy.json seed.

        Called once at startup. Idempotent — skips capabilities that already
        exist in the policy_events projection.
        """
        self._kernel = kernel

        path = Path(settings.capability_policy_path)
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))

        for name in data.get("forbidden", []):
            self._ensure_policy(kernel, name, "forbidden")
        for name in data.get("needs_user", []):
            self._ensure_policy(kernel, name, "high")
        for name in data.get("auto_allow", []):
            self._ensure_policy(kernel, name, "low")

    def _ensure_policy(self, kernel, capability: str, risk: str) -> None:
        existing = kernel.query_state("policy_events", capability=capability, limit=1)
        if existing:
            return
        kernel.emit_event(
            "PolicyCreated",
            "policy",
            f"policy_{capability}",
            payload={"capability": capability, "risk_level": risk},
            actor="kernel",
        )

    # ── Risk lookup (reads policy_events projection) ──────────────────

    def risk_for(self, name: str, kernel=None, mcp_default_high: bool = False) -> str:
        """Return 'forbidden', 'high', or 'low'.

        If kernel is provided, reads from policy_events projection (event-sourced).
        Falls back to external tool registry for dynamic MCP tools.
        Gracefully tolerates missing policy_events table (tests/ad-hoc Kernels).
        """
        # External MCP tools (not in event-sourced projection yet)
        if name in self._external_forbidden:
            return "forbidden"
        if name in self._external_needs_user:
            return "high"
        if name in self._external_auto_allow:
            return "low"

        # Event-sourced policy (from policy_events projection)
        if kernel is not None:
            try:
                rows = kernel.query_state("policy_events", capability=name, status="active", limit=1)
                if rows:
                    risk_level = rows[0].get("risk_level", "low")
                    if risk_level == "forbidden":
                        return "forbidden"
                    if risk_level == "high":
                        return "high"
                    return "low"
            except Exception:
                import logging
                logging.getLogger(__name__).debug(
                    "CapabilityPolicy: policy table may not exist", exc_info=True
                )

        # Unknown capability: default
        return "high" if mcp_default_high else "low"

    # ── External MCP tools (event-sourced via PolicyCreated/Updated/Revoked) ──

    def register_external_tool(self, name: str, *, risk: str) -> None:
        """Register an external MCP tool policy and emit the appropriate event.

        Emits PolicyCreated/PolicyUpdated to the event log FIRST (projection
        is the single source of truth), then updates the in-memory cache.
        Previously the in-memory cache was updated before the emit, which
        could leave it stale if the emit failed.
        """
        # Emit event for event-sourced persistence (projection = SSOT)
        if self._kernel is not None:
            existing_rows = self._kernel.query_state("policy_events", capability=name, limit=1)
            if existing_rows:
                existing = existing_rows[0]
                if existing.get("status") == "revoked":
                    self._kernel.emit_event(
                        "PolicyCreated", "policy", f"policy_{name}",
                        payload={"capability": name, "risk_level": risk},
                        actor="kernel",
                    )
                else:
                    existing_risk = existing.get("risk_level")
                    if existing_risk != risk:
                        self._kernel.emit_event(
                            "PolicyUpdated", "policy", f"policy_{name}",
                            payload={"capability": name, "risk_level": risk},
                            actor="kernel",
                        )
            else:
                self._kernel.emit_event(
                    "PolicyCreated", "policy", f"policy_{name}",
                    payload={"capability": name, "risk_level": risk},
                    actor="kernel",
                )

        # Update in-memory cache AFTER emit (read-through mirror of projection)
        self._external_auto_allow.discard(name)
        self._external_needs_user.discard(name)
        self._external_forbidden.discard(name)
        if risk == "forbidden":
            self._external_forbidden.add(name)
        elif risk == "high":
            self._external_needs_user.add(name)
        else:
            self._external_auto_allow.add(name)

    def clear_external_tools(self) -> None:
        """Revoke all external tool policies and clear in-memory cache.

        Emits PolicyRevoked for each registered tool so that rebuild("policy")
        correctly reflects that external tools are no longer active.
        """
        all_names = self._external_auto_allow | self._external_needs_user | self._external_forbidden
        if self._kernel is not None and all_names:
            for name in all_names:
                self._kernel.emit_event(
                    "PolicyRevoked",
                    "policy",
                    f"policy_{name}",
                    payload={"capability": name},
                    actor="kernel",
                )

        self._external_auto_allow.clear()
        self._external_needs_user.clear()
        self._external_forbidden.clear()

    def all_registered_tools(self, kernel=None) -> set[str]:
        result: set[str] = self._external_auto_allow | self._external_needs_user | self._external_forbidden
        if kernel is not None:
            rows = kernel.query_state("policy_events", status="active", limit=500)
            for row in rows:
                result.add(row.get("capability", ""))
        return result

    def is_forbidden(self, name: str, kernel=None) -> bool:
        return self.risk_for(name, kernel=kernel) == "forbidden"

    def reset(self) -> None:
        """Clear in-memory caches — for test isolation.

        The event-sourced projection (policy_events) remains intact;
        only the fast-path cache is cleared. Next risk_for() call will
        re-derive from the projection.
        """
        self._external_auto_allow.clear()
        self._external_needs_user.clear()
        self._external_forbidden.clear()
        self._kernel = None


capability_policy = CapabilityPolicy()

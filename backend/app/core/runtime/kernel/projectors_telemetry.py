"""Telemetry projection — derives the tool_calls table solely from
Capability* events.

v0.3.0: closes the tool_calls half of ARCHITECTURE_SURVIVAL_REVIEW Critical #1.
Previously tool_calls was written directly by mcp_hub.invoke_tool while
CapabilityInvoked was emitted in parallel by kernel.invoke_capability — a
classic dual-write that could drift. The table is now a governed projection:
every row is derived from a Capability* event, the table can be rebuilt via
kernel.rebuild("capability"), and verify_tool_calls_audit.py can guarantee
1:1 correspondence because the INSERT path no longer exists outside the Kernel.

Note: llm_calls remains APP_STORAGE for now (pending LLMCallRecorded event,
see Phase 2.2). Only tool_calls is migrated in this commit.
"""

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["capability"] = ["tool_calls"]


@projector("CapabilityInvoked")
def _on_capability_invoked(event: Event, conn) -> None:
    p = event.payload
    # event.seq is the global monotonic ordinal — use it as the row PK so
    # each capability call maps to exactly one tool_calls row, and rebuild
    # converges byte-identically.
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

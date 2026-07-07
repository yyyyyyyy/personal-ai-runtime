"""Telemetry projection — derives tool_calls and llm_calls tables solely from
Capability* and LLMCallRecorded events.

v0.3.0: closes ARCHITECTURE_SURVIVAL_REVIEW Critical #1 (dual-write drift).
Previously tool_calls was written directly by mcp_hub.invoke_tool and
llm_calls by telemetry.record_llm_call, while CapabilityInvoked and (now)
LLMCallRecorded were emitted in parallel — classic dual-writes that could
drift. Both tables are now governed projections: every row is derived from
an event, both tables are rebuildable, and verify scripts guarantee 1:1
correspondence.
"""
from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

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
            latency_ms, cost, success, error_message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            event.ts,
        ),
    )

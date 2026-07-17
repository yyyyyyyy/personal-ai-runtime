"""LLM / tool-call telemetry read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def query_llm_calls(*, days: int | None = None, limit: int = 5000, offset: int = 0) -> list[dict[str, Any]]:
    """Governed llm_calls projection via Kernel ABI."""
    filters: dict[str, Any] = {"limit": limit, "offset": offset}
    if days is not None:
        filters["since_days"] = days
    return kernel().query_state("llm_calls", **filters)


def query_tool_calls(
    *,
    days: int | None = None,
    tool_name: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Governed tool_calls projection via Kernel ABI."""
    filters: dict[str, Any] = {"limit": limit}
    if days is not None:
        filters["since_days"] = days
    if tool_name:
        filters["tool_name"] = tool_name
    return kernel().query_state("tool_calls", **filters)


def summarize_llm_calls(*, days: int = 7) -> dict[str, Any]:
    """Full-window LLM cost/token/latency summary (SQL aggregate)."""
    return kernel().aggregate_state("llm_calls_summary", since_days=days)


def summarize_llm_calls_by_model(*, days: int = 7) -> list[dict[str, Any]]:
    """LLM totals grouped by provider+model (SQL aggregate)."""
    return kernel().aggregate_state("llm_calls_by_model", since_days=days)


def summarize_tool_calls(*, days: int = 7) -> list[dict[str, Any]]:
    """Tool-call totals grouped by tool_name (SQL aggregate)."""
    return kernel().aggregate_state("tool_calls_summary", since_days=days)


def summarize_call_failure_rates(*, days: int = 1) -> dict[str, Any]:
    """LLM/tool failure rates over a window (SQL aggregate)."""
    return kernel().aggregate_state("call_failure_rates", since_days=days)


def query_recent_tool_names(*, limit: int = 3) -> list[str]:
    """Return the names of the most recently invoked capabilities."""
    try:
        events = kernel().read_events(type="CapabilityInvoked", limit=limit, order="desc")
        names: list[str] = []
        for evt in events:
            name = evt.payload.get("name", "")
            if name and name not in names:
                names.append(name)
        return names[:limit]
    except Exception:
        return []

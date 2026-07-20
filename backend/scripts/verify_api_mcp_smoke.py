#!/usr/bin/env python3
"""Smoke-check the core MCP tool registry and FastAPI route surface.

Tool inventory is derived from ``MCPHub.CORE_CATEGORIES`` registration so
adding a core tool does not require updating this script. Two pins still
fail CI on silent shrinkage:

* ``CRITICAL_TOOLS`` — essential tools that must never disappear
* ``MIN_CORE_TOOL_COUNT`` — floor on total core registration size
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import prepare_script_env

# Must never silently disappear — intentional product contract pin.
# Includes the historical EXPECTED_TOOLS set from the pre-registry smoke check.
CRITICAL_TOOLS = frozenset({
    "get_current_time",
    "read_file",
    "write_file",
    "apply_patch",
    "list_directory",
    "search_files",
    "web_search",
    "fetch_url",
    "list_calendar_events",
    "add_calendar_event",
    "get_upcoming_events",
    "check_inbox",
    "read_inbox_email",
    "mark_inbox_email_read",
    "send_email",
    "shell_exec",
    "git_status",
    "git_log",
    "git_diff",
    "create_goal",
    "update_goal_progress",
    "complete_goal",
    "list_active_goals",
})

# Floor on CORE_CATEGORIES registration size. Bump when you intentionally add
# core tools; lower only with an explicit product decision (update this constant).
MIN_CORE_TOOL_COUNT = 26

SENSITIVE_TOOLS = (
    "write_file",
    "apply_patch",
    "send_email",
    "add_calendar_event",
    "shell_exec",
)

EXPECTED_ROUTE_PREFIXES = {
    "/api/chat/conversations",
    "/api/chat/approvals/",
    "/api/work-items/",
    "/api/memory/memories",
    "/api/memory/memories/grouped",
    "/api/memory/portrait",
    "/api/notifications/",
    "/api/system/health",
    "/api/telemetry/",
    "/api/approvals/",
    "/api/tasks/background",
    "/api/triggers/",
    "/api/inbox/",
}


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _core_registered_tools() -> set[str]:
    """Tool names registered when only CORE_CATEGORIES are enabled."""
    from app.core.harness.mcp_hub import MCPHub

    hub = MCPHub(enabled_categories=set(MCPHub.CORE_CATEGORIES))
    return set(hub._tools)


def verify_mcp_tools() -> int:
    from app.core.harness.mcp_hub import mcp_hub

    core_tools = _core_registered_tools()
    if len(core_tools) < MIN_CORE_TOOL_COUNT:
        return _fail(
            f"Core registration shrank below floor: "
            f"{len(core_tools)} < {MIN_CORE_TOOL_COUNT} "
            f"(update MIN_CORE_TOOL_COUNT only for intentional reductions)"
        )

    missing_critical = CRITICAL_TOOLS - core_tools
    if missing_critical:
        return _fail(f"Core registration lost critical tools: {missing_critical}")

    tools = mcp_hub.get_tool_defs_for_llm()
    actual = {tool["function"]["name"] for tool in tools}
    missing = core_tools - actual
    if missing:
        return _fail(f"Runtime hub missing core tools: {missing}")

    for tool_name in SENSITIVE_TOOLS:
        if not mcp_hub.needs_confirmation(tool_name):
            return _fail(f"{tool_name} must require confirmation")
    if not mcp_hub.is_async("web_search"):
        return _fail("web_search must be asynchronous")

    print(
        f"OK: {len(tools)} MCP tools registered "
        f"(core={len(core_tools)}, critical={len(CRITICAL_TOOLS)}, "
        f"floor={MIN_CORE_TOOL_COUNT})"
    )
    return 0


def verify_api_routes() -> int:
    import app.main as main_module

    try:
        from fastapi.routing import iter_route_contexts

        routes = [
            context.path
            for context in iter_route_contexts(main_module.app.routes)
            if context.path is not None
        ]
    except ImportError:
        routes = []
        for route in main_module.app.routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                routes.append(path)

    missing = {
        prefix
        for prefix in EXPECTED_ROUTE_PREFIXES
        if not any(route.startswith(prefix) for route in routes)
    }
    if missing:
        return _fail(f"Missing API route prefixes: {missing}")
    print(f"OK: {len(EXPECTED_ROUTE_PREFIXES)} core API modules loaded")
    return 0


def main() -> int:
    prepare_script_env()
    with tempfile.TemporaryDirectory(
        prefix="personal-ai-runtime-smoke-",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        data_dir = Path(temp_dir)
        os.environ.update(
            {
                "LLM_API_KEY": "test-key",
                "DATA_DIR": str(data_dir),
                "SQLITE_PATH": str(data_dir / "smoke.db"),
                "VECTOR_DIR": str(data_dir / "vectors"),
                "MCP_EXTERNAL_ENABLED": "false",
            }
        )
        rc = verify_mcp_tools()
        if rc != 0:
            return rc
        return verify_api_routes()


if __name__ == "__main__":
    raise SystemExit(main())

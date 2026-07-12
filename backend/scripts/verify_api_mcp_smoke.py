#!/usr/bin/env python3
"""Smoke-check the core MCP tool registry and FastAPI route surface."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

EXPECTED_TOOLS = {
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
    "open_web_page",
    "search_and_extract",
    "shell_exec",
    "git_status",
    "git_log",
    "git_diff",
    "telegram_send",
    "telegram_updates",
    "create_goal",
    "update_goal_progress",
    "complete_goal",
    "list_active_goals",
}

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


def verify_mcp_tools() -> None:
    from app.core.harness.mcp_hub import mcp_hub

    tools = mcp_hub.get_tool_defs_for_llm()
    actual = {tool["function"]["name"] for tool in tools}
    missing = EXPECTED_TOOLS - actual
    assert not missing, f"Missing builtin tools: {missing}"
    assert len(actual) >= len(EXPECTED_TOOLS), (
        f"Expected at least {len(EXPECTED_TOOLS)} builtin tools, got {len(actual)}"
    )

    for tool_name in (
        "write_file",
        "apply_patch",
        "send_email",
        "add_calendar_event",
        "shell_exec",
    ):
        assert mcp_hub.needs_confirmation(tool_name), (
            f"{tool_name} must require confirmation"
        )
    for tool_name in ("web_search", "telegram_send"):
        assert mcp_hub.is_async(tool_name), f"{tool_name} must be asynchronous"

    print(f"OK: {len(tools)} MCP tools registered")


def verify_api_routes() -> None:
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
    assert not missing, f"Missing API route prefixes: {missing}"
    print(f"OK: {len(EXPECTED_ROUTE_PREFIXES)} core API modules loaded")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="personal-ai-runtime-smoke-") as temp_dir:
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
        verify_mcp_tools()
        verify_api_routes()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

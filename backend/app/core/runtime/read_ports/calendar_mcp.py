"""Calendar, world-model, and MCP connector read ports."""

from __future__ import annotations

import json
from datetime import date as date_type
from typing import Any


def query_world_context() -> str:
    from app.core.agents.world_model import world_model

    return world_model.to_prompt_context()


def query_calendar_upcoming(*, days: int = 7) -> dict[str, Any]:
    from app.core.harness.builtin_tools.calendar import calendar_server

    raw = calendar_server.get_upcoming(days=days)
    return json.loads(raw)


def query_calendar_today_events() -> dict[str, Any]:
    from app.core.harness.builtin_tools.calendar import calendar_server

    today = date_type.today().isoformat()
    raw = calendar_server.list_events(date=today, days=1)
    return json.loads(raw)


def get_mcp_server_status(server_name: str) -> dict[str, Any]:
    """Get status info for an external MCP server via MCPMesh."""
    from app.core.harness.mcp_mesh import mcp_mesh

    conn = mcp_mesh._connections.get(server_name)
    if conn and conn.session is not None:
        return {"connected": True, "tool_count": len(conn.tools)}
    return {"connected": False, "tool_count": 0}


def get_mcp_server_tools(server_name: str) -> list[dict[str, str]]:
    """Get list of tools from an external MCP server via MCPMesh."""
    from app.core.harness.mcp_mesh import mcp_mesh

    conn = mcp_mesh._connections.get(server_name)
    if not conn or not conn.tools:
        return []
    return [
        {"name": t.name, "description": (getattr(t, "description", "") or "")[:100]}
        for t in conn.tools
    ]


def test_mcp_connection(server_name: str) -> dict[str, Any]:
    """Test connection to an external MCP server."""
    status = get_mcp_server_status(server_name)
    if status.get("connected"):
        return {"status": "ok", "message": f"连接器 {server_name} 运行正常", "tool_count": status.get("tool_count", 0)}
    return {"status": "error", "message": f"连接器 {server_name} 未连接"}


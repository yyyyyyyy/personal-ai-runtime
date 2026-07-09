"""Connectors API — manage external service connectors (MCP servers).

Includes registry for discovering and installing community MCP servers.
"""

import json as _json
import logging
from pathlib import Path as _Path

from fastapi import APIRouter, HTTPException

from app.api.models import InstallConnectorRequest
from app.core.harness.mcp_config import (
    ExternalMCPServerConfig,
    load_external_server_configs,
)
from app.core.runtime import read_ports

router = APIRouter(tags=["connectors"])
logger = logging.getLogger(__name__)


def _get_connector_status(config: ExternalMCPServerConfig) -> dict:
    """Build status info for a connector."""
    server_info = read_ports.get_mcp_server_status(config.name)
    is_connected = server_info.get("connected", False) if server_info else False
    tool_count = server_info.get("tool_count", 0) if server_info else 0

    return {
        "name": config.name,
        "enabled": config.enabled,
        "available": config.is_available(),
        "connected": is_connected,
        "tool_count": tool_count,
        "has_credentials": config.has_required_credentials(),
        "required_env": config.required_env,
        "description": _get_connector_description(config.name),
    }


def _get_connector_description(name: str) -> str:
    """Get human-readable description for known connectors."""
    descriptions = {
        "brave": "网页搜索 (Brave Search)",
        "github": "GitHub 代码仓库集成",
        "notion": "Notion 文档和知识库",
        "calendar": "日历事件管理",
        "mail": "邮件收发管理",
        "tavily": "AI 搜索引擎 (Tavily)",
        "context7": "文档上下文增强 (Context7)",
    }
    return descriptions.get(name, f"外部连接器: {name}")


@router.get("/")
async def list_connectors():
    """List all available connectors with their status."""
    configs = load_external_server_configs()

    # Built-in connector names
    builtin_names = {"mail", "calendar"}

    # External connectors (exclude any that shadow a built-in name)
    connectors = [
        _get_connector_status(config)
        for config in configs
        if config.name not in builtin_names
    ]

    builtin = [
        {
            "name": "mail",
            "enabled": True,
            "available": True,
            "connected": True,
            "tool_count": 3,
            "has_credentials": True,
            "required_env": [],
            "description": "邮件收发管理",
            "builtin": True,
        },
        {
            "name": "calendar",
            "enabled": True,
            "available": True,
            "connected": True,
            "tool_count": 3,
            "has_credentials": True,
            "required_env": [],
            "description": "日历事件管理",
            "builtin": True,
        },
    ]

    return {"connectors": builtin + connectors}


@router.get("/{connector_name}")
async def get_connector(connector_name: str):
    """Get detailed info for a specific connector."""
    configs = load_external_server_configs()

    # Check built-in connectors
    if connector_name in ("mail", "calendar"):
        return {
            "name": connector_name,
            "enabled": True,
            "available": True,
            "connected": True,
            "tool_count": 3,
            "has_credentials": True,
            "required_env": [],
            "description": _get_connector_description(connector_name),
            "builtin": True,
            "tools": _get_builtin_tools(connector_name),
        }

    # Check external connectors
    for config in configs:
        if config.name == connector_name:
            status = _get_connector_status(config)
            tools = read_ports.get_mcp_server_tools(config.name)
            if tools:
                status["tools"] = tools[:20]
            return status

    raise HTTPException(status_code=404, detail=f"Connector '{connector_name}' not found")


def _get_builtin_tools(name: str) -> list[dict]:
    """Get tools for built-in connectors."""
    if name == "mail":
        return [
            {"name": "check_inbox", "description": "检查收件箱新邮件"},
            {"name": "send_email", "description": "发送邮件"},
            {"name": "read_inbox_email", "description": "读取邮件详情"},
        ]
    if name == "calendar":
        return [
            {"name": "list_calendar_events", "description": "列出日历事件"},
            {"name": "add_calendar_event", "description": "创建日历事件"},
            {"name": "get_upcoming_events", "description": "获取即将到来的事件"},
        ]
    return []


@router.post("/{connector_name}/test")
async def test_connector(connector_name: str):
    """Test connection to a connector."""
    configs = load_external_server_configs()

    # Built-in connectors are always working
    if connector_name in ("mail", "calendar"):
        return {"status": "ok", "message": "内置连接器运行正常"}

    for config in configs:
        if config.name == connector_name:
            if not config.is_available():
                return {
                    "status": "error",
                    "message": f"连接器不可用: 缺少必要的环境变量 {config.required_env}",
                }

            # Try to connect via read_ports
            result = read_ports.test_mcp_connection(config.name)
            return result

    raise HTTPException(status_code=404, detail=f"Connector '{connector_name}' not found")


# ── MCP Registry APIs (community marketplace) ────────────────────────────

_REGISTRY_PATH = _Path(__file__).resolve().parent.parent.parent / "mcp_registry.json"
MCP_CONFIG_PATH = _Path(__file__).resolve().parent.parent.parent / "mcp_config.json"


def _load_registry() -> list[dict]:
    if not _REGISTRY_PATH.exists():
        return []
    try:
        return _json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to load connector registry from %s", _REGISTRY_PATH, exc_info=True)
        return []


@router.get("/registry")
async def list_registry():
    registry = _load_registry()
    return {"servers": registry, "total": len(registry)}


@router.post("/install")
async def install_new_connector(body: InstallConnectorRequest):
    server_name = body.name.strip()
    if not server_name:
        raise HTTPException(status_code=400, detail="Server name is required")
    registry = _load_registry()
    entry = next((s for s in registry if s["name"] == server_name), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found in registry")
    if MCP_CONFIG_PATH.exists():
        existing = _json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        existing = {"servers": [], "external_servers": []}
    external = existing.get("external_servers", [])
    if any(s.get("name") == server_name for s in external):
        return {"ok": False, "message": f"'{server_name}' is already installed"}
    new_entry = {
        "name": server_name, "type": "stdio",
        "command": entry["install_command"], "args": entry.get("install_args", []),
        "env": entry.get("env_vars", {}), "enabled_tools": entry.get("enabled_tools", ["*"]),
        "policy_default": "auto_allow", "startup_connect": True,
        "description": entry.get("description", ""),
    }
    external.append(new_entry)
    existing["external_servers"] = external
    MCP_CONFIG_PATH.write_text(_json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "message": f"'{server_name}' installed. Restart the backend to activate.", "server": new_entry}


@router.post("/uninstall")
async def uninstall_connector(body: dict):
    server_name = body.get("name", "").strip()
    if not server_name:
        raise HTTPException(status_code=400, detail="Server name is required")
    if not MCP_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="mcp_config.json not found")
    existing = _json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    external = existing.get("external_servers", [])
    filtered = [s for s in external if s.get("name") != server_name]
    if len(filtered) == len(external):
        return {"ok": False, "message": f"'{server_name}' is not installed"}
    existing["external_servers"] = filtered
    MCP_CONFIG_PATH.write_text(_json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "message": f"'{server_name}' uninstalled. Restart the backend to apply."}

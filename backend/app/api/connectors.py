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

# Static paths must be declared before /{connector_name} or FastAPI will treat
# "registry" / "install" as connector names.
_REGISTRY_PATH = _Path(__file__).resolve().parent.parent.parent / "mcp_registry.json"
MCP_CONFIG_PATH = _Path(__file__).resolve().parent.parent.parent / "mcp_config.json"


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


_BUILTIN_DESCRIPTIONS = {
    "mail": "邮件收发管理",
    "calendar": "日历事件管理",
}

# (mtime, parsed entries) — invalidate when mcp_registry.json changes on disk.
_registry_cache: tuple[float, list[dict]] | None = None


def _load_registry() -> list[dict]:
    global _registry_cache
    if not _REGISTRY_PATH.exists():
        _registry_cache = None
        return []
    try:
        mtime = _REGISTRY_PATH.stat().st_mtime
        cached = _registry_cache
        if cached is not None and cached[0] == mtime:
            return cached[1]
        data = _json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("mcp_registry.json must be a list at %s", _REGISTRY_PATH)
            return []
        _registry_cache = (mtime, data)
        return data
    except Exception:
        logger.warning("Failed to load connector registry from %s", _REGISTRY_PATH, exc_info=True)
        return []


def _registry_entry(name: str) -> dict | None:
    for server in _load_registry():
        if isinstance(server, dict) and server.get("name") == name:
            return server
    return None


def _get_connector_description(name: str) -> str:
    """Prefer marketplace description from mcp_registry.json."""
    entry = _registry_entry(name)
    if entry:
        description = entry.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return _BUILTIN_DESCRIPTIONS.get(name, f"外部连接器: {name}")


def _runtime_entry_from_registry(entry: dict) -> dict:
    """Build an mcp_config external_servers item from registry metadata.

    ``env_vars`` values are UI hints only — never copied into runtime ``env``.
    """
    optional_env = entry.get("optional_env")
    if not isinstance(optional_env, list):
        optional_env = []

    required_env = entry.get("required_env")
    if not isinstance(required_env, list):
        env_vars = entry.get("env_vars") or {}
        keys = list(env_vars.keys()) if isinstance(env_vars, dict) else []
        optional_set = set(optional_env)
        required_env = [key for key in keys if key not in optional_set]

    new_entry: dict = {
        "name": entry["name"],
        "type": "stdio",
        "enabled": True,
        "command": entry["install_command"],
        "args": list(entry.get("install_args") or []),
        "policy_default": entry.get("policy_default") or "auto_allow",
        "startup_connect": bool(entry.get("startup_connect", True)),
        "required_env": required_env,
        "optional_env": optional_env,
        "enabled_tools": list(entry.get("enabled_tools") or []),
        "needs_user_tools": list(entry.get("needs_user_tools") or []),
        "ingestion_tools": list(entry.get("ingestion_tools") or []),
        "description": entry.get("description") or "",
    }
    timeout = entry.get("connect_timeout_seconds")
    if isinstance(timeout, (int, float)) and timeout > 0:
        new_entry["connect_timeout_seconds"] = timeout
    return new_entry


def _get_builtin_tools(name: str) -> list[dict]:
    """Get tools for built-in connectors."""
    if name == "mail":
        return [
            {"name": "check_inbox", "description": "检查收件箱新邮件"},
            {"name": "read_inbox_email", "description": "读取邮件详情"},
            {"name": "mark_inbox_email_read", "description": "标记邮件为已读"},
            {"name": "mark_inbox_email_unread", "description": "标记邮件为未读"},
            {"name": "send_email", "description": "发送邮件"},
        ]
    if name == "calendar":
        return [
            {"name": "list_calendar_events", "description": "列出日历事件"},
            {"name": "add_calendar_event", "description": "创建日历事件"},
            {"name": "get_upcoming_events", "description": "获取即将到来的事件"},
        ]
    return []


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
            "tool_count": 4,
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


def _load_installed_names() -> set[str]:
    """Return the set of server names already in mcp_config.json."""
    if not MCP_CONFIG_PATH.exists():
        return set()
    try:
        existing = _json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
        external = existing.get("external_servers", [])
        return {s["name"] for s in external if isinstance(s, dict) and "name" in s}
    except Exception:
        logger.warning("Failed to load installed MCP servers from %s", MCP_CONFIG_PATH, exc_info=True)
        return set()


@router.get("/registry")
async def list_registry():
    registry = _load_registry()
    installed_names = _load_installed_names()
    enriched = []
    for server in registry:
        enriched.append({
            **server,
            "installed": server.get("name", "") in installed_names,
        })
    return {"servers": enriched, "total": len(enriched)}


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
    new_entry = _runtime_entry_from_registry(entry)
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

"""Keep mcp_registry runtime fields aligned with mcp_config."""

from __future__ import annotations

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = BACKEND_ROOT / "mcp_config.json"
REGISTRY_PATH = BACKEND_ROOT / "mcp_registry.json"

_LIST_FIELDS = (
    "required_env",
    "optional_env",
    "enabled_tools",
    "needs_user_tools",
    "ingestion_tools",
)


def _list_field(entry: dict, key: str) -> list:
    value = entry.get(key, [])
    return list(value) if isinstance(value, list) else []


def test_registry_runtime_fields_match_mcp_config():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_name = {entry["name"]: entry for entry in registry}

    for server in config.get("external_servers", []):
        name = server["name"]
        assert name in by_name, f"{name} missing from mcp_registry.json"
        reg = by_name[name]
        assert reg.get("install_command") == server.get("command")
        assert reg.get("install_args") == server.get("args"), (
            f"{name}: registry install_args must match mcp_config args"
        )
        assert bool(reg.get("startup_connect", True)) == bool(
            server.get("startup_connect", True)
        ), f"{name}: startup_connect mismatch"
        assert (reg.get("policy_default") or "auto_allow") == (
            server.get("policy_default") or "auto_allow"
        ), f"{name}: policy_default mismatch"
        assert reg.get("connect_timeout_seconds") == server.get(
            "connect_timeout_seconds"
        ), f"{name}: connect_timeout_seconds mismatch"
        for key in _LIST_FIELDS:
            assert _list_field(reg, key) == _list_field(server, key), (
                f"{name}: {key} mismatch"
            )


def test_runtime_entry_from_registry_omits_env_hints():
    from app.api.connectors import _runtime_entry_from_registry

    entry = {
        "name": "brave",
        "install_command": "npx",
        "install_args": ["-y", "@brave/brave-search-mcp-server"],
        "env_vars": {"BRAVE_API_KEY": "从 https://brave.com/search/api/ 获取"},
        "required_env": ["BRAVE_API_KEY"],
        "enabled_tools": ["brave_web_search"],
        "ingestion_tools": ["brave_web_search"],
        "startup_connect": False,
        "policy_default": "auto_allow",
        "description": "Brave 网页搜索",
    }
    runtime = _runtime_entry_from_registry(entry)
    assert "env" not in runtime
    assert runtime["required_env"] == ["BRAVE_API_KEY"]
    assert runtime["args"] == entry["install_args"]
    assert runtime["startup_connect"] is False


def test_runtime_entry_optional_env_not_promoted_to_required():
    from app.api.connectors import _runtime_entry_from_registry

    entry = {
        "name": "context7",
        "install_command": "npx",
        "install_args": ["-y", "@upstash/context7-mcp"],
        "env_vars": {"CONTEXT7_API_KEY": "可选"},
        "optional_env": ["CONTEXT7_API_KEY"],
        "description": "docs",
    }
    runtime = _runtime_entry_from_registry(entry)
    assert runtime["required_env"] == []
    assert runtime["optional_env"] == ["CONTEXT7_API_KEY"]

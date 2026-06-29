"""Load and validate MCP mesh configuration from mcp_config.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def normalize_tool_name(name: str) -> str:
    """Normalize MCP tool name for LLM registration (alphanumeric + underscore)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def external_tool_id(server_name: str, tool_name: str) -> str:
    """Build a stable, collision-resistant capability name."""
    return f"{server_name}_{normalize_tool_name(tool_name)}"


def mcp_external_enabled() -> bool:
    """Single source of truth for whether external MCP mesh is active."""
    from app.config import settings

    return settings.mcp_external_enabled


def parse_mcp_servers_enabled() -> set[str] | None:
    """Optional env override: comma-separated server names. None = use json config."""
    from app.config import settings

    raw = settings.mcp_servers_enabled.strip()
    if not raw or raw == "*":
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


@dataclass
class ExternalMCPServerConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    tool_prefix: str = ""
    policy_default: str = "auto_allow"  # auto_allow | needs_user | forbidden
    needs_user_tools: list[str] = field(default_factory=list)
    needs_user_patterns: list[str] = field(default_factory=list)
    ingestion_tools: list[str] = field(default_factory=list)
    ingestion_patterns: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    optional_env: list[str] = field(default_factory=list)
    enabled_tools: list[str] = field(default_factory=list)
    startup_connect: bool = True
    connect_timeout_seconds: float = 45.0
    call_timeout_seconds: float = 30.0

    @property
    def registration_prefix(self) -> str:
        return self.tool_prefix or self.name

    def is_available(self) -> bool:
        """Server can start when required env vars are set (or none required)."""
        if not self.enabled:
            return False
        if self.required_env:
            return self.has_required_credentials()
        return True

    def resolve_env(self) -> dict[str, str]:
        from app.config import settings

        settings_env = {
            "BRAVE_API_KEY": settings.brave_api_key,
            "CONTEXT7_API_KEY": settings.context7_api_key,
            "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_personal_access_token,
            "TAVILY_API_KEY": settings.tavily_api_key,
            "NOTION_TOKEN": settings.notion_token,
        }
        merged = dict(self.env)
        for key in self.required_env + self.optional_env:
            val = settings_env.get(key, "").strip()
            if val:
                merged[key] = val
        return merged

    def has_required_credentials(self) -> bool:
        env = self.resolve_env()
        return all(env.get(key, "").strip() for key in self.required_env)

    def should_expose_tool(self, tool_name: str) -> bool:
        if not self.enabled_tools:
            return True
        return tool_name in self.enabled_tools

    def tool_needs_user(self, tool_name: str) -> bool:
        if tool_name in self.needs_user_tools:
            return True
        for pattern in self.needs_user_patterns:
            if pattern in tool_name or (
                pattern.endswith("*") and tool_name.startswith(pattern[:-1])
            ):
                return True
        return self.policy_default == "needs_user"

    def tool_is_ingestion(self, tool_name: str) -> bool:
        if tool_name in self.ingestion_tools:
            return True
        for pattern in self.ingestion_patterns:
            if pattern in tool_name or (
                pattern.endswith("*") and tool_name.startswith(pattern[:-1])
            ):
                return True
        return False


def load_mcp_config(path: str | Path | None = None) -> dict[str, Any]:
    from app.config import settings

    config_path = Path(path or settings.mcp_config_path)
    if not config_path.is_file():
        return {"servers": [], "external_servers": []}
    return json.loads(config_path.read_text(encoding="utf-8"))


def load_external_server_configs(path: str | Path | None = None) -> list[ExternalMCPServerConfig]:
    from app.config import settings

    if not mcp_external_enabled():
        return []

    allowed = parse_mcp_servers_enabled()
    data = load_mcp_config(path)
    configs: list[ExternalMCPServerConfig] = []
    for raw in data.get("external_servers", []):
        if raw.get("type", "stdio") != "stdio":
            continue
        name = raw.get("name", "")
        command = raw.get("command", "")
        if not name or not command:
            continue
        if allowed is not None and name not in allowed:
            continue
        call_timeout = float(raw.get("call_timeout_seconds", settings.tool_timeout_seconds))
        configs.append(
            ExternalMCPServerConfig(
                name=name,
                command=command,
                args=list(raw.get("args", [])),
                env=dict(raw.get("env", {})),
                enabled=bool(raw.get("enabled", True)),
                tool_prefix=str(raw.get("tool_prefix", "")),
                policy_default=str(raw.get("policy_default", "auto_allow")),
                needs_user_tools=list(raw.get("needs_user_tools", [])),
                needs_user_patterns=list(raw.get("needs_user_patterns", [])),
                ingestion_tools=list(raw.get("ingestion_tools", [])),
                ingestion_patterns=list(raw.get("ingestion_patterns", [])),
                required_env=list(raw.get("required_env", [])),
                optional_env=list(raw.get("optional_env", [])),
                enabled_tools=list(raw.get("enabled_tools", [])),
                startup_connect=bool(raw.get("startup_connect", True)),
                connect_timeout_seconds=float(raw.get("connect_timeout_seconds", 45)),
                call_timeout_seconds=call_timeout,
            )
        )
    return configs

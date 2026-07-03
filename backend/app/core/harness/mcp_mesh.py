"""MCP Mesh — manages stdio MCP server connections and tool discovery."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool as MCPTool

from app.core.harness.mcp_config import (
    ExternalMCPServerConfig,
    external_tool_id,
    load_external_server_configs,
)
from app.core.harness.url_safety import UnsafeUrlError, validate_http_url

logger = logging.getLogger(__name__)

# Playwright tools that accept outbound URLs — validated before invoke.
_PLAYWRIGHT_URL_TOOLS: dict[str, str] = {
    "browser_navigate": "url",
}


@dataclass
class DiscoveredMCPTool:
    registered_name: str
    server_name: str
    original_name: str
    description: str
    parameters: dict[str, Any]
    requires_confirmation: bool
    is_ingestion: bool
    policy_risk: str  # low | high | forbidden


class _ServerConnection:
    def __init__(self, config: ExternalMCPServerConfig):
        self.config = config
        self.session: ClientSession | None = None
        self._transport: tuple | None = None  # (read_stream, write_stream)
        self.tools: list[MCPTool] = []
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._connect_lock:
            if self.session is not None:
                return
            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.resolve_env() or None,
            )
            transport = stdio_client(params)
            read, write = await transport.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await asyncio.wait_for(
                session.initialize(),
                timeout=self.config.connect_timeout_seconds,
            )
            listed = await asyncio.wait_for(
                session.list_tools(),
                timeout=self.config.connect_timeout_seconds,
            )
            self.session = session
            self._transport = (transport, read, write)
            self.tools = list(listed.tools)

    async def close(self) -> None:
        """Best-effort cleanup — swallow all errors so shutdown never breaks."""
        if self.session is not None:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Error closing MCP session for server %s", self.config.name, exc_info=True
                )
        self.session = None
        if self._transport is not None:
            transport, _read, _write = self._transport
            try:
                await transport.__aexit__(None, None, None)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Error closing MCP transport for server %s", self.config.name, exc_info=True
                )
        self._transport = None
        self.tools = []


class MCPMesh:
    """Lifecycle manager for external stdio MCP servers."""

    def __init__(self) -> None:
        self._connections: dict[str, _ServerConnection] = {}
        self._pending_configs: dict[str, ExternalMCPServerConfig] = {}
        self._tool_index: dict[str, tuple[str, str]] = {}
        self._discovered: list[DiscoveredMCPTool] = []
        self._started = False
        self._start_lock = asyncio.Lock()
        self._register_lock = asyncio.Lock()
        self._lazy_task: asyncio.Task | None = None

    @property
    def discovered_tools(self) -> list[DiscoveredMCPTool]:
        return list(self._discovered)

    def is_external_tool(self, name: str) -> bool:
        return name in self._tool_index

    async def start(self) -> list[DiscoveredMCPTool]:
        async with self._start_lock:
            if self._started:
                return self.discovered_tools

            configs = load_external_server_configs()
            startup_configs = [c for c in configs if c.is_available() and c.startup_connect]
            lazy_configs = [c for c in configs if c.is_available() and not c.startup_connect]

            for config in lazy_configs:
                self._pending_configs[config.name] = config

            if startup_configs:
                await self._connect_servers_parallel(startup_configs)

            self._started = True

            if lazy_configs:
                self._lazy_task = asyncio.create_task(
                    self._connect_lazy_servers(lazy_configs),
                    name="mcp-mesh-lazy-connect",
                )

            return self.discovered_tools

    async def stop(self) -> None:
        async with self._start_lock:
            if self._lazy_task is not None:
                self._lazy_task.cancel()
                try:
                    await self._lazy_task
                except asyncio.CancelledError:
                    pass
                self._lazy_task = None

            from app.core.harness.mcp_hub import mcp_hub
            from app.core.runtime.capability_governance import capability_governance
            from app.core.runtime.taint import (
                clear_external_ingestion_tools,
                clear_external_write_tools,
            )

            for name in list(self._tool_index):
                mcp_hub.unregister_tool(name)
            capability_governance.clear_external_tools()
            clear_external_ingestion_tools()
            clear_external_write_tools()

            for conn in self._connections.values():
                try:
                    await conn.close()
                except Exception:
                    logger.exception("Error closing MCP server '%s'", conn.config.name)
            self._connections.clear()
            self._pending_configs.clear()
            self._tool_index.clear()
            self._discovered.clear()
            self._started = False

    async def call_tool(self, registered_name: str, arguments: dict[str, Any]) -> str:
        if registered_name not in self._tool_index:
            return json.dumps({"error": f"Unknown external tool: {registered_name}"})

        server_name, original_name = self._tool_index[registered_name]
        try:
            conn = await self._ensure_server(server_name)
        except Exception as exc:
            return json.dumps({"error": f"MCP server unavailable ({server_name}): {exc}"})

        url_err = self._validate_tool_arguments(original_name, arguments)
        if url_err:
            return json.dumps({"error": url_err})

        try:
            result = await asyncio.wait_for(
                conn.session.call_tool(original_name, arguments),  # type: ignore[union-attr]
                timeout=conn.config.call_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return json.dumps({"error": f"MCP tool timed out: {registered_name}"})
        except Exception as exc:
            return json.dumps({"error": f"MCP tool failed: {exc}"})

        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(block))
        if result.isError:
            return json.dumps({"error": "\n".join(parts) or "MCP tool returned error"})
        return "\n".join(parts) if parts else json.dumps({"status": "ok", "result": None})

    async def _connect_servers_parallel(self, configs: list[ExternalMCPServerConfig]) -> None:
        results = await asyncio.gather(
            *[self._connect_server_safe(config) for config in configs],
            return_exceptions=True,
        )
        for config, result in zip(configs, results):
            if isinstance(result, Exception):
                logger.warning(
                    "MCP server '%s' unavailable: %s",
                    config.name,
                    type(result).__name__,
                )

    async def _connect_lazy_servers(self, configs: list[ExternalMCPServerConfig]) -> None:
        for config in configs:
            try:
                await self._connect_server_safe(config)
                self._pending_configs.pop(config.name, None)
            except Exception as e:
                logger.warning(
                    "MCP server '%s' (lazy connect) unavailable: %s",
                    config.name,
                    type(e).__name__,
                )

    async def _connect_server_safe(self, config: ExternalMCPServerConfig) -> list[DiscoveredMCPTool]:
        discovered = await self._connect_server(config)
        await self._register_discovered_tools(discovered)
        logger.info(
            "MCP server '%s' connected with %d tools",
            config.name,
            len(discovered),
        )
        return discovered

    async def _register_discovered_tools(self, discovered: list[DiscoveredMCPTool]) -> None:
        if not discovered:
            return
        async with self._register_lock:
            from app.core.harness.mcp_hub import mcp_hub

            mcp_hub.register_mesh_tools(discovered)

    async def _ensure_server(self, server_name: str) -> _ServerConnection:
        conn = self._connections.get(server_name)
        if conn is not None and conn.session is not None:
            return conn

        config = self._pending_configs.get(server_name)
        if config is None:
            raise RuntimeError(f"server not connected: {server_name}")

        await self._connect_server_safe(config)
        self._pending_configs.pop(server_name, None)
        conn = self._connections.get(server_name)
        if conn is None or conn.session is None:
            raise RuntimeError(f"server connect failed: {server_name}")
        return conn

    def _validate_tool_arguments(self, original_name: str, arguments: dict[str, Any]) -> str | None:
        url_field = _PLAYWRIGHT_URL_TOOLS.get(original_name)
        if not url_field:
            return None
        url = arguments.get(url_field)
        if not url or not isinstance(url, str):
            return None
        try:
            validate_http_url(url)
        except UnsafeUrlError as exc:
            return f"Blocked URL: {exc}"
        return None

    async def _connect_server(self, config: ExternalMCPServerConfig) -> list[DiscoveredMCPTool]:
        conn = _ServerConnection(config)
        await conn.connect()
        self._connections[config.name] = conn

        discovered: list[DiscoveredMCPTool] = []
        for tool in conn.tools:
            if not config.should_expose_tool(tool.name):
                continue

            registered = external_tool_id(config.registration_prefix, tool.name)
            if registered in self._tool_index:
                registered = external_tool_id(config.name, tool.name)

            needs_user = config.tool_needs_user(tool.name)
            ingestion = config.tool_is_ingestion(tool.name)
            if config.policy_default == "forbidden":
                risk = "forbidden"
            elif needs_user:
                risk = "high"
            else:
                risk = "low"

            parameters = tool.inputSchema if isinstance(tool.inputSchema, dict) else {
                "type": "object",
                "properties": {},
            }

            discovered.append(
                DiscoveredMCPTool(
                    registered_name=registered,
                    server_name=config.name,
                    original_name=tool.name,
                    description=tool.description or f"MCP tool {tool.name} from {config.name}",
                    parameters=parameters,
                    requires_confirmation=needs_user,
                    is_ingestion=ingestion,
                    policy_risk=risk,
                )
            )
            self._tool_index[registered] = (config.name, tool.name)

        self._discovered.extend(discovered)
        return discovered

    def get_server_status(self) -> dict:
        """Return connection status for external MCP servers."""
        from app.core.harness.mcp_config import load_external_server_configs, mcp_external_enabled

        if not mcp_external_enabled():
            return {
                "enabled": False,
                "servers": [],
                "total_tools": 0,
            }

        connected = set(self._connections.keys())
        servers = []
        for config in load_external_server_configs():
            if not config.is_available():
                servers.append({
                    "name": config.name,
                    "status": "unavailable",
                    "reason": "missing_env",
                    "tool_count": 0,
                })
                continue
            if config.name in connected:
                conn = self._connections[config.name]
                servers.append({
                    "name": config.name,
                    "status": "connected",
                    "tool_count": len(conn.tools),
                    "startup_connect": config.startup_connect,
                })
            elif config.name in self._pending_configs:
                servers.append({
                    "name": config.name,
                    "status": "lazy",
                    "tool_count": 0,
                    "startup_connect": config.startup_connect,
                })
            else:
                servers.append({
                    "name": config.name,
                    "status": "disconnected",
                    "tool_count": 0,
                    "startup_connect": config.startup_connect,
                })

        return {
            "enabled": True,
            "servers": servers,
            "total_tools": len(self._discovered),
        }


mcp_mesh = MCPMesh()

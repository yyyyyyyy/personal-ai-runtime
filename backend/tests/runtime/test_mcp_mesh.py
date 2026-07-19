"""Tests for MCP mesh URL validation and taint integration."""

import pytest

from app.core.harness.mcp_hub import ToolDef, mcp_hub
from app.core.harness.mcp_mesh import MCPMesh
from app.core.runtime.capability_governance import capability_governance
from app.core.runtime.kernel import Kernel
from app.core.runtime.taint import register_external_write_tool, taint_registry
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "mcp_mesh.db"))
    return Kernel(db=db)


@pytest.mark.asyncio
async def test_playwright_navigate_blocks_internal_url():
    mesh = MCPMesh()
    err = await mesh._validate_tool_arguments("browser_navigate", {"url": "http://127.0.0.1/"})
    assert err is not None
    assert "Blocked URL" in err


@pytest.mark.asyncio
async def test_playwright_navigate_allows_public_url():
    mesh = MCPMesh()
    err = await mesh._validate_tool_arguments("browser_navigate", {"url": "https://example.com"})
    assert err is None


@pytest.mark.asyncio
async def test_any_http_url_argument_blocked():
    """SSRF checks apply to any http(s) string arg, not only browser_navigate."""
    mesh = MCPMesh()
    err = await mesh._validate_tool_arguments(
        "fetch_page",
        {"target": "http://169.254.169.254/latest/meta-data"},
    )
    assert err is not None
    assert "Blocked URL" in err


@pytest.mark.asyncio
async def test_url_named_field_with_non_http_scheme_still_checked():
    mesh = MCPMesh()
    err = await mesh._validate_tool_arguments("open", {"href": "file:///etc/passwd"})
    assert err is not None
    assert "Blocked URL" in err


@pytest.mark.asyncio
async def test_nested_url_argument_blocked():
    mesh = MCPMesh()
    err = await mesh._validate_tool_arguments(
        "nested_fetch",
        {"request": {"headers": {}, "url": "http://127.0.0.1/admin"}},
    )
    assert err is not None
    assert "Blocked URL" in err


def test_forbidden_mesh_tools_omitted_from_llm_schema():
    from app.core.harness.mcp_hub import MCPHub
    from app.core.harness.mcp_mesh import DiscoveredMCPTool
    from app.core.runtime.capability_governance import capability_governance

    hub = MCPHub(enabled_categories=set())
    discovered = [
        DiscoveredMCPTool(
            registered_name="ext_forbidden_tool",
            server_name="ext",
            original_name="danger",
            description="should not appear",
            parameters={"type": "object", "properties": {}},
            requires_confirmation=True,
            is_ingestion=False,
            policy_risk="forbidden",
        ),
        DiscoveredMCPTool(
            registered_name="ext_ok_tool",
            server_name="ext",
            original_name="ok",
            description="visible",
            parameters={"type": "object", "properties": {}},
            requires_confirmation=False,
            is_ingestion=False,
            policy_risk="low",
        ),
    ]
    hub.register_mesh_tools(discovered)
    names = {t["function"]["name"] for t in hub.get_tool_defs_for_llm()}
    assert "ext_forbidden_tool" not in names
    assert "ext_ok_tool" in names
    assert hub.get_tool("ext_forbidden_tool") is None
    capability_governance.clear_external_tools()
    hub.unregister_tool("ext_ok_tool")


@pytest.mark.asyncio
async def test_forbidden_tools_not_indexed_for_call():
    """Forbidden discoveries must not be callable via mesh.call_tool."""
    mesh = MCPMesh()
    mesh._tool_index["ext_ok_tool"] = ("ext", "ok")
    # Simulate discovery skipping forbidden from the index.
    assert "ext_forbidden_tool" not in mesh._tool_index
    assert mesh.is_external_tool("ext_ok_tool")
    assert not mesh.is_external_tool("ext_forbidden_tool")

    result = await mesh.call_tool("ext_forbidden_tool", {})
    assert "Unknown external tool" in result


@pytest.mark.asyncio
async def test_discovery_skips_forbidden_in_tool_index():
    """policy_default=forbidden tools enter _discovered but not _tool_index."""
    from unittest.mock import AsyncMock, MagicMock

    from app.core.harness import mcp_mesh as mesh_mod
    from app.core.harness.mcp_config import ExternalMCPServerConfig

    mesh = MCPMesh()
    cfg = ExternalMCPServerConfig(
        name="locked",
        command="true",
        args=[],
        policy_default="forbidden",
    )
    tool = MagicMock()
    tool.name = "danger"
    tool.description = "x"
    tool.inputSchema = {"type": "object", "properties": {}}

    class FakeConn:
        def __init__(self, config):
            self.config = config
            self.session = object()
            self.tools = [tool]
            self.connect = AsyncMock()
            self.close = AsyncMock()

    original = mesh_mod._ServerConnection
    mesh_mod._ServerConnection = FakeConn  # type: ignore[misc]
    try:
        discovered = await mesh._connect_server(cfg)
    finally:
        mesh_mod._ServerConnection = original  # type: ignore[misc]

    assert len(discovered) == 1
    assert discovered[0].policy_risk == "forbidden"
    assert discovered[0].registered_name not in mesh._tool_index
    assert "locked" in mesh._discovered_servers
    assert mesh.is_external_tool(discovered[0].registered_name) is False


def test_builtin_categories_opt_in_keeps_core(monkeypatch):
    """Listing an advanced category must not replace CORE."""
    import app.config as config_module
    from app.config import reset_settings
    from app.core.harness.mcp_hub import MCPHub

    reset_settings()
    monkeypatch.setattr(config_module.settings, "builtin_tool_categories", "telegram")
    hub = MCPHub()
    assert "filesystem" in hub._enabled_categories
    assert "shell" in hub._enabled_categories
    assert "telegram" in hub._enabled_categories
    # Explicit empty set still means "register nothing" for tests.
    empty = MCPHub(enabled_categories=set())
    assert empty._enabled_categories == set()


@pytest.mark.asyncio
async def test_ensure_server_reconnects_dead_session():
    """A connection with session=None must reconnect using stored config."""
    from unittest.mock import MagicMock

    from app.core.harness.mcp_config import ExternalMCPServerConfig

    mesh = MCPMesh()
    cfg = ExternalMCPServerConfig(name="demo", command="true", args=[])
    mesh._configs["demo"] = cfg
    dead = MagicMock()
    dead.session = None
    dead.config = cfg
    mesh._connections["demo"] = dead

    live = MagicMock()
    live.session = object()
    live.config = cfg
    live.tools = []

    async def fake_connect_safe(config):
        mesh._connections[config.name] = live
        return []

    mesh._connect_server_safe = fake_connect_safe  # type: ignore[method-assign]
    conn = await mesh._ensure_server("demo")
    assert conn is live
    assert conn.session is not None


def test_transport_failure_classifier():
    from app.core.harness.mcp_mesh import _is_transport_failure

    assert _is_transport_failure(ConnectionError("reset"))
    assert _is_transport_failure(BrokenPipeError())
    assert _is_transport_failure(RuntimeError("session closed"))
    assert not _is_transport_failure(ValueError("bad arg"))
    assert not _is_transport_failure(RuntimeError("tool rejected by server"))


@pytest.mark.asyncio
async def test_call_with_reconnect_skips_app_errors():
    """Non-transport failures must not reconnect/retry."""
    from unittest.mock import AsyncMock, MagicMock

    mesh = MCPMesh()
    session = MagicMock()
    session.call_tool = AsyncMock(side_effect=ValueError("invalid tool args"))
    conn = MagicMock()
    conn.session = session
    conn.config.call_timeout_seconds = 5.0

    mark = AsyncMock()
    mesh._mark_disconnected = mark  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="invalid tool args"):
        await mesh._call_with_reconnect(conn, "demo", "ok", {}, "demo_ok")
    mark.assert_not_awaited()
    assert session.call_tool.await_count == 1


@pytest.mark.asyncio
async def test_call_with_reconnect_retries_transport_once():
    """Transport failure closes session, reconnects, and retries exactly once."""
    from unittest.mock import AsyncMock, MagicMock

    mesh = MCPMesh()
    ok_result = MagicMock()
    ok_result.content = []
    ok_result.isError = False

    first_session = MagicMock()
    first_session.call_tool = AsyncMock(side_effect=ConnectionError("broken pipe"))
    first_conn = MagicMock()
    first_conn.session = first_session
    first_conn.config.call_timeout_seconds = 5.0

    second_session = MagicMock()
    second_session.call_tool = AsyncMock(return_value=ok_result)
    second_conn = MagicMock()
    second_conn.session = second_session
    second_conn.config.call_timeout_seconds = 5.0

    mesh._mark_disconnected = AsyncMock()  # type: ignore[method-assign]
    mesh._ensure_server = AsyncMock(return_value=second_conn)  # type: ignore[method-assign]

    result = await mesh._call_with_reconnect(
        first_conn, "demo", "ok", {"x": 1}, "demo_ok"
    )
    assert result is ok_result
    mesh._mark_disconnected.assert_awaited_once_with("demo")
    mesh._ensure_server.assert_awaited_once_with("demo")
    assert first_session.call_tool.await_count == 1
    assert second_session.call_tool.await_count == 1


@pytest.mark.asyncio
async def test_connect_failure_cleans_up_partial_session():
    """initialize() failure must __aexit__ session and transport."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.core.harness.mcp_config import ExternalMCPServerConfig
    from app.core.harness.mcp_mesh import _ServerConnection

    cfg = ExternalMCPServerConfig(name="flaky", command="true", args=[])
    conn = _ServerConnection(cfg)

    transport = MagicMock()
    transport.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    transport.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.initialize = AsyncMock(side_effect=RuntimeError("handshake failed"))

    with patch(
        "app.core.harness.mcp_mesh.stdio_client", return_value=transport
    ), patch(
        "app.core.harness.mcp_mesh.ClientSession", return_value=session
    ), patch.object(cfg, "resolve_env", return_value={}):
        with pytest.raises(RuntimeError, match="handshake failed"):
            await conn.connect()

    session.__aexit__.assert_awaited_once()
    transport.__aexit__.assert_awaited_once()
    assert conn.session is None
    assert conn._transport is None


@pytest.mark.asyncio
async def test_reconnect_does_not_rediscover_forbidden_only_server():
    """Servers already discovered (even if all tools forbidden) skip rediscovery."""
    from unittest.mock import AsyncMock, MagicMock

    from app.core.harness.mcp_config import ExternalMCPServerConfig
    from app.core.harness.mcp_mesh import DiscoveredMCPTool

    mesh = MCPMesh()
    cfg = ExternalMCPServerConfig(
        name="locked",
        command="true",
        args=[],
        policy_default="forbidden",
    )
    mesh._configs["locked"] = cfg
    mesh._discovered_servers.add("locked")
    mesh._discovered.append(
        DiscoveredMCPTool(
            registered_name="locked_danger",
            server_name="locked",
            original_name="danger",
            description="x",
            parameters={"type": "object", "properties": {}},
            requires_confirmation=True,
            is_ingestion=False,
            policy_risk="forbidden",
        )
    )

    tool = MagicMock()
    tool.name = "danger"
    tool.description = "x"
    tool.inputSchema = {"type": "object", "properties": {}}

    live = MagicMock()
    live.session = object()
    live.config = cfg
    live.tools = [tool]
    live.connect = AsyncMock()
    live.close = AsyncMock()

    from app.core.harness import mcp_mesh as mesh_mod

    original = mesh_mod._ServerConnection

    class FakeConn:
        def __init__(self, config):
            self.config = config
            self.session = object()
            self.tools = [tool]
            self.connect = AsyncMock()
            self.close = AsyncMock()

    mesh_mod._ServerConnection = FakeConn  # type: ignore[misc]
    try:
        discovered = await mesh._connect_server(cfg)
    finally:
        mesh_mod._ServerConnection = original  # type: ignore[misc]

    assert discovered == []
    assert len(mesh._discovered) == 1


@pytest.mark.asyncio
async def test_external_write_tool_taint_escalation(kernel, monkeypatch):
    """External needs_user tools participate in taint escalation."""
    tool_name = "github_create_issue"

    async def fake_invoke(name, args):
        return '{"ok": true}'

    monkeypatch.setattr(mcp_hub, "invoke_tool", fake_invoke)
    mcp_hub.register_tool(
        ToolDef(
            name=tool_name,
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=fake_invoke,
            is_async=True,
            requires_confirmation=True,
        )
    )
    capability_governance.register_external_tool(tool_name, risk="high")
    register_external_write_tool(tool_name)

    corr = "corr-ext-write"
    taint_registry.mark(corr, source="external_ingestion", reason="web_search")
    result = await kernel.invoke_capability(
        name=tool_name,
        args={"title": "x"},
        actor="user",
        correlation_id=corr,
    )
    assert result["status"] == "pending"
    mcp_hub.unregister_tool(tool_name)
    capability_governance.clear_external_tools()
    taint_registry.clear(corr)


def test_get_server_status_single_server(monkeypatch):
    mesh = MCPMesh()
    monkeypatch.setattr(
        "app.core.harness.mcp_config.mcp_external_enabled",
        lambda: True,
    )

    class Cfg:
        name = "email"
        startup_connect = True

        @staticmethod
        def is_available():
            return True

    monkeypatch.setattr(
        "app.core.harness.mcp_config.load_external_server_configs",
        lambda: [Cfg()],
    )
    status = mesh.get_server_status("email")
    assert status["name"] == "email"
    assert status["connected"] is False
    assert status["status"] == "disconnected"
    assert status["tool_count"] == 0
    assert mesh.list_server_tools("email") == []

"""MCPHub invoke_tool observability and kwargs filtering."""

import json

import pytest

from app.core.harness.mcp_hub import MCPHub, ToolDef


@pytest.mark.asyncio
async def test_invoke_tool_logs_and_returns_error_on_failure(monkeypatch):
    from unittest.mock import MagicMock

    import app.core.harness.mcp_hub as hub_mod

    hub = MCPHub(enabled_categories=set())
    logged = MagicMock()
    monkeypatch.setattr(hub_mod.logger, "exception", logged)

    def boom() -> str:
        raise RuntimeError("kaboom")

    hub.register_tool(ToolDef(
        name="boom_tool",
        description="x",
        parameters={"type": "object", "properties": {}},
        handler=boom,
    ))
    result = await hub.invoke_tool("boom_tool", {})
    payload = json.loads(result)
    assert "kaboom" in payload["error"]
    logged.assert_called_once()
    assert logged.call_args.args[0] == "Tool %s failed"
    assert logged.call_args.args[1] == "boom_tool"


@pytest.mark.asyncio
async def test_invoke_tool_filters_unexpected_kwargs():
    hub = MCPHub(enabled_categories=set())
    seen: dict = {}

    def echo(path: str) -> str:
        seen["path"] = path
        return path

    hub.register_tool(ToolDef(
        name="echo_path",
        description="x",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=echo,
    ))
    result = await hub.invoke_tool("echo_path", {"path": "/a", "noise": True})
    assert result == "/a"
    assert seen == {"path": "/a"}


@pytest.mark.asyncio
async def test_get_tool_defs_skips_forbidden():
    from app.core.runtime.capability_governance import capability_governance

    hub = MCPHub(enabled_categories=set())
    hub.register_tool(ToolDef(
        name="ok_tool",
        description="visible",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "ok",
    ))
    hub.register_tool(ToolDef(
        name="deny_tool",
        description="hidden",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "no",
    ))
    capability_governance.register_external_tool("deny_tool", risk="forbidden")
    try:
        names = {t["function"]["name"] for t in hub.get_tool_defs_for_llm()}
        assert "ok_tool" in names
        assert "deny_tool" not in names
    finally:
        capability_governance.clear_external_tools()

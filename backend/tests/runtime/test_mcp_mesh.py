"""Tests for MCP mesh URL validation and taint integration."""

import pytest

from app.core.harness.mcp_hub import ToolDef, mcp_hub
from app.core.harness.mcp_mesh import MCPMesh
from app.core.runtime.capability_policy import capability_policy
from app.core.runtime.kernel import Kernel
from app.core.runtime.taint import register_external_write_tool, taint_registry
from app.store.database import Database


@pytest.fixture
def kernel(tmp_path):
    db = Database(db_path=str(tmp_path / "mcp_mesh.db"))
    return Kernel(db=db)


def test_playwright_navigate_blocks_internal_url():
    mesh = MCPMesh()
    err = mesh._validate_tool_arguments("browser_navigate", {"url": "http://127.0.0.1/"})
    assert err is not None
    assert "Blocked URL" in err


def test_playwright_navigate_allows_public_url():
    mesh = MCPMesh()
    err = mesh._validate_tool_arguments("browser_navigate", {"url": "https://example.com"})
    assert err is None


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
    capability_policy.register_external_tool(tool_name, risk="high")
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
    capability_policy.clear_external_tools()
    taint_registry.clear(corr)

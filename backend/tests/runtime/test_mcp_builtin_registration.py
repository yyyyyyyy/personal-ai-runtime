"""Table-driven builtin registration contracts."""

import pytest

from app.core.harness import mcp_builtin_registration as reg
from app.core.harness.mcp_hub import MCPHub, ToolDef


def test_category_builders_cover_hub_categories():
    expected = set(MCPHub.CORE_CATEGORIES) | set(MCPHub.ADVANCED_CATEGORIES)
    assert set(reg._CATEGORY_BUILDERS) == expected


def test_core_registration_tool_count():
    hub = MCPHub(enabled_categories=set(MCPHub.CORE_CATEGORIES))
    assert len(hub._tools) == 26
    assert "read_file" in hub._tools
    assert "telegram_send" not in hub._tools
    assert "computer_screenshot" not in hub._tools


def test_builtin_browser_tools_removed():
    """Browser automation lives in external Playwright MCP, not builtins."""
    hub = MCPHub(enabled_categories=set(MCPHub.CORE_CATEGORIES) | set(MCPHub.ADVANCED_CATEGORIES))
    removed = {"open_web_page", "search_and_extract", "take_screenshot", "browser_navigate"}
    assert removed.isdisjoint(hub._tools)
    assert "browser" not in hub._enabled_categories
    assert "browser" not in reg._CATEGORY_BUILDERS


def test_advanced_opt_in_adds_tools():
    cats = set(MCPHub.CORE_CATEGORIES) | {"telegram", "computer_use"}
    hub = MCPHub(enabled_categories=cats)
    assert "telegram_send" in hub._tools
    assert "computer_screenshot" in hub._tools
    assert hub.needs_confirmation("computer_screenshot")
    assert hub.is_async("read_file")


def test_offload_specs_are_async():
    for spec in reg._filesystem_specs():
        assert spec.offload is True
    hub = MCPHub(enabled_categories={"filesystem"})
    for name in ("read_file", "write_file", "list_directory"):
        assert hub.is_async(name)


@pytest.mark.asyncio
async def test_offload_preserves_signature_for_kwargs_filter():
    """Extra LLM kwargs must be dropped before the threaded sync handler runs."""
    import inspect

    from app.core.harness.mcp_hub import _filter_tool_kwargs

    def sync_handler(path: str) -> str:
        return path

    wrapped = reg._offload(sync_handler)
    sig = inspect.signature(wrapped)
    assert "path" in sig.parameters
    assert not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())

    filtered = _filter_tool_kwargs(wrapped, {"path": "/tmp/a", "extra": 1})
    assert filtered == {"path": "/tmp/a"}

    hub = MCPHub(enabled_categories=set())
    hub.register_tool(ToolDef(
        name="t_read",
        description="x",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=wrapped,
        is_async=True,
    ))
    result = await hub.invoke_tool("t_read", {"path": "/tmp/a", "bogus": True})
    assert result == "/tmp/a"

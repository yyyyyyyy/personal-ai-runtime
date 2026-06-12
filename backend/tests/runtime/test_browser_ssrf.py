"""SSRF regression tests for browser MCP server."""

import json

import pytest

from app.core.harness.mcp_servers.browser import browser_server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/",
    ],
)
async def test_browser_blocks_internal_urls(url: str):
    result = json.loads(await browser_server.open_page(url))
    assert "error" in result
    assert "Blocked URL" in result["error"]

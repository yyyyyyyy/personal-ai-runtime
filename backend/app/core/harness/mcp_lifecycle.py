"""MCP mesh startup/shutdown — harness lifecycle hooks for FastAPI."""

from __future__ import annotations

import logging

from app.core.harness.mcp_config import mcp_external_enabled
from app.core.harness.mcp_mesh import mcp_mesh

logger = logging.getLogger(__name__)


async def start_mcp_mesh() -> int:
    """Connect startup MCP servers; lazy servers connect in background."""
    if not mcp_external_enabled():
        return 0
    await mcp_mesh.start()
    return len(mcp_mesh.discovered_tools)


async def stop_mcp_mesh() -> None:
    """Disconnect external MCP servers and unregister tools.

    Always invoke ``stop`` (idempotent) so a runtime flip of
    ``mcp_external_enabled`` cannot leave stdio children / registered tools
    behind.
    """
    await mcp_mesh.stop()

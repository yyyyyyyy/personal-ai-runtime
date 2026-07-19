"""Runtime Gateway MCP Server — exposes Personal AI Runtime's HTTP surface
to external agents (Cursor, Claude Code, any MCP-compatible client).

Built on the official ``mcp`` FastMCP SDK (stdio). Tool logic lives in
``tools.py`` and talks to the local backend over HTTP — it does NOT import
runtime internals.

Tools (``PAR_GATEWAY_TOOLS=all|core|name,name``):
  - core: recall / store_memory — @public memory + knowledge
  - extended: list_pending_approvals / recent_timeline — authenticated read surfaces

Usage from Cursor / Claude Desktop config:
  {
    "mcpServers": {
      "personal-ai-runtime": {
        "command": "python3",
        "args": ["-m", "mcp_servers.runtime_gateway.server"],
        "env": {
          "PAR_BASE_URL": "http://localhost:8000",
          "PAR_AUTH_TOKEN": "<your AUTH_TOKEN>",
          "PAR_GATEWAY_TOOLS": "all"
        }
      }
    }
  }
"""

# NOTE: do not enable ``from __future__ import annotations`` here — FastMCP
# inspects live type objects when registering tools and breaks on stringized hints.
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.runtime_gateway.http_client import (
    HttpResult,
    configure_base_url,
    env_flag,
)
from mcp_servers.runtime_gateway.http_client import (
    request as _http,
)
from mcp_servers.runtime_gateway.http_client import (
    validate_base_url as _validate_base_url,
)
from mcp_servers.runtime_gateway.tools import (
    ToolOutput,
    resolve_enabled_tools,
    tool_list_pending_approvals,
    tool_recall,
    tool_recent_timeline,
    tool_store_memory,
)

logger = logging.getLogger("runtime_gateway")


def _read_gateway_version() -> str:
    """Prefer backend app.version without importing ``app`` (keeps gateway decoupled)."""
    try:
        version_path = Path(__file__).resolve().parents[2] / "app" / "version.py"
        text = version_path.read_text(encoding="utf-8")
        match = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "1.0.0"


GATEWAY_VERSION = _read_gateway_version()
GATEWAY_NAME = "personal-ai-runtime"
ENABLED_TOOLS = resolve_enabled_tools()

mcp = FastMCP(
    GATEWAY_NAME,
    instructions=(
        "Personal AI Runtime gateway. Use recall before answering personal "
        "questions; store_memory for durable user facts. "
        "list_pending_approvals and recent_timeline are read-only when enabled."
    ),
)


def _apply_server_version(server: FastMCP, version: str) -> None:
    """Set MCP serverInfo.version.

    FastMCP 1.x constructs the low-level Server without a version kwarg, so we
    assign the public ``version`` attribute when present.
    """
    lowlevel = getattr(server, "_mcp_server", None)
    if lowlevel is not None and hasattr(lowlevel, "version"):
        lowlevel.version = version


_apply_server_version(mcp, GATEWAY_VERSION)


def _unwrap(output: ToolOutput) -> str:
    """Return tool text, or raise so FastMCP marks the call as isError."""
    if output.is_error:
        raise ValueError(output.text)
    return output.text


def _register_tools() -> None:
    if "recall" in ENABLED_TOOLS:

        @mcp.tool()
        def recall(query: str, n_results: int = 5) -> str:
            """Recall what the user already knows. Searches memories + knowledge documents."""
            return _unwrap(tool_recall(query, n_results))

    if "store_memory" in ENABLED_TOOLS:

        @mcp.tool()
        def store_memory(content: str, category: str = "fact") -> str:
            """Store a durable fact about the user into long-term memory."""
            return _unwrap(tool_store_memory(content, category))

    if "list_pending_approvals" in ENABLED_TOOLS:

        @mcp.tool()
        def list_pending_approvals(limit: int = 20) -> str:
            """List pending capability approvals waiting for the user (read-only)."""
            return _unwrap(tool_list_pending_approvals(limit))

    if "recent_timeline" in ENABLED_TOOLS:

        @mcp.tool()
        def recent_timeline(n_results: int = 15, event_type: str = "") -> str:
            """Fetch recent human-readable timeline events (read-only)."""
            return _unwrap(tool_recent_timeline(n_results, event_type or None))


_register_tools()


def _configure_logging() -> None:
    """Log to stderr only — stdout is reserved for MCP JSON-RPC."""
    root = logging.getLogger("runtime_gateway")
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    if env_flag("PAR_LOG_JSON"):
        class _JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload: dict[str, Any] = {
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(payload, ensure_ascii=False)

        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False


def main() -> None:
    _configure_logging()
    try:
        configure_base_url()
    except ValueError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
    logger.info(
        "starting %s v%s (stdio) tools=%s",
        GATEWAY_NAME,
        GATEWAY_VERSION,
        ",".join(sorted(ENABLED_TOOLS)),
    )
    mcp.run(transport="stdio")


__all__ = [
    "ENABLED_TOOLS",
    "GATEWAY_NAME",
    "GATEWAY_VERSION",
    "HttpResult",
    "ToolOutput",
    "_http",
    "_unwrap",
    "_validate_base_url",
    "main",
    "mcp",
    "tool_list_pending_approvals",
    "tool_recall",
    "tool_recent_timeline",
    "tool_store_memory",
]


if __name__ == "__main__":
    main()

"""MCP Client Hub — manages tool registration, discovery, and invocation.

Supports both sync and async tool handlers. Phase 2 adds web search, fetch, and
enhanced filesystem tools backed by dedicated server modules.
"""

import json
import inspect
from typing import Any, Callable, Awaitable
from dataclasses import dataclass

from app.mcp_servers.filesystem import filesystem_server
from app.mcp_servers.web_search import web_search_server
from app.mcp_servers.fetch import fetch_server


@dataclass
class ToolDef:
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict
    handler: Callable[..., str]
    is_async: bool = False
    requires_confirmation: bool = False


class MCPHub:
    """Central hub for managing tools and routing LLM tool calls."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}
        self._register_all_tools()

    def _register_all_tools(self):
        self._register_time_tools()
        self._register_filesystem_tools()
        self._register_web_tools()

    def _register_time_tools(self):
        from datetime import datetime

        def handle_get_current_time(timezone: str = "Asia/Shanghai") -> str:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(timezone)
            except Exception:
                tz = None
            now = datetime.now(tz=tz)
            return json.dumps({
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": now.strftime("%A"),
                "timezone": timezone,
            })

        self.register_tool(ToolDef(
            name="get_current_time",
            description="Get the current date and time in a specified timezone (defaults to Asia/Shanghai).",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone name, e.g. 'Asia/Shanghai'.",
                    }
                },
            },
            handler=handle_get_current_time,
        ))

    def _register_filesystem_tools(self):
        self.register_tool(ToolDef(
            name="read_file",
            description="Read the contents of a text file. Returns the file content as plain text.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to read."},
                    "max_lines": {"type": "integer", "description": "Maximum number of lines to return (default 500)."},
                },
                "required": ["path"],
            },
            handler=filesystem_server.read_file,
        ))

        self.register_tool(ToolDef(
            name="write_file",
            description="Write content to a file. WARNING: This requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to write."},
                    "content": {"type": "string", "description": "Content to write to the file."},
                },
                "required": ["path", "content"],
            },
            handler=filesystem_server.write_file,
            requires_confirmation=True,
        ))

        self.register_tool(ToolDef(
            name="list_directory",
            description="List files and subdirectories at a given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the directory to list."},
                    "pattern": {"type": "string", "description": "Optional glob pattern to filter results (e.g. '*.md')."},
                },
                "required": ["path"],
            },
            handler=filesystem_server.list_directory,
        ))

        self.register_tool(ToolDef(
            name="search_files",
            description="Search for files by name recursively under a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory to search in."},
                    "query": {"type": "string", "description": "Filename query (partial match)."},
                },
                "required": ["path", "query"],
            },
            handler=filesystem_server.search_files,
        ))

    def _register_web_tools(self):
        async def handle_web_search(query: str, max_results: int = 5) -> str:
            return await web_search_server.search(query, max_results)

        self.register_tool(ToolDef(
            name="web_search",
            description="Search the web for information. Use this when you need current information or facts you're unsure about.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "max_results": {"type": "integer", "description": "Maximum number of results (default 5)."},
                },
                "required": ["query"],
            },
            handler=handle_web_search,
            is_async=True,
        ))

        async def handle_fetch_url(url: str, extract_text: bool = True) -> str:
            return await fetch_server.fetch_url(url, extract_text)

        self.register_tool(ToolDef(
            name="fetch_url",
            description="Fetch and extract content from a web page URL. Returns the page title and readable text.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch."},
                    "extract_text": {"type": "boolean", "description": "If true, extract readable text. If false, return raw HTML."},
                },
                "required": ["url"],
            },
            handler=handle_fetch_url,
            is_async=True,
        ))

    def register_tool(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def get_tool_defs_for_llm(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def get_tool(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def needs_confirmation(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.requires_confirmation if tool else False

    def is_async(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.is_async if tool else False

    async def invoke_tool(self, name: str, arguments: dict) -> str:
        """Invoke a tool by name. Supports both sync and async handlers. Returns the result string."""
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            if tool.is_async:
                result = await tool.handler(**arguments)
            else:
                result = tool.handler(**arguments)

            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + "\n... [output truncated]"
            return result
        except Exception as e:
            return json.dumps({"error": str(e)})


# Global singleton
mcp_hub = MCPHub()

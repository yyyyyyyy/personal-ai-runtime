"""MCP Client Hub — manages tool registration, discovery, and invocation.

Supports both sync and async tool handlers. Phase 2 adds web search, fetch, and
enhanced filesystem tools backed by dedicated server modules.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable

from app.core.harness.mcp_servers.browser import browser_server
from app.core.harness.mcp_servers.calendar import calendar_server
from app.core.harness.mcp_servers.clipboard_ocr import clipboard_ocr_server
from app.core.harness.mcp_servers.email import email_server
from app.core.harness.mcp_servers.fetch import fetch_server
from app.core.harness.mcp_servers.filesystem import filesystem_server
from app.core.harness.mcp_servers.git import git_server
from app.core.harness.mcp_servers.shell import shell_server
from app.core.harness.mcp_servers.telegram_bot import telegram_bot_server
from app.core.harness.mcp_servers.web_search import web_search_server
from app.core.telemetry.telemetry import ToolCallRecord, telemetry


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
        self._load_external_servers()

    def _register_all_tools(self):
        self._register_time_tools()
        self._register_filesystem_tools()
        self._register_web_tools()
        self._register_calendar_tools()
        self._register_email_tools()
        self._register_browser_tools()
        self._register_clipboard_ocr_tools()
        self._register_shell_tools()
        self._register_git_tools()
        self._register_telegram_tools()

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

    def _register_calendar_tools(self):
        self.register_tool(ToolDef(
            name="list_calendar_events",
            description="List calendar events for a date range. Check what's happening on specific days.",
            parameters={
                "type": "object",
                "properties": {
                    "calendar": {"type": "string", "description": "Calendar name (default: 'default')."},
                    "date": {"type": "string", "description": "Start date in YYYY-MM-DD format."},
                    "days": {"type": "integer", "description": "Number of days to look ahead (default 7)."},
                },
            },
            handler=calendar_server.list_events,
        ))

        self.register_tool(ToolDef(
            name="add_calendar_event",
            description="Add an event to your calendar. Requires user confirmation for scheduling.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "date": {"type": "string", "description": "Event date in YYYY-MM-DD format."},
                    "time": {"type": "string", "description": "Event time in HH:MM format (default 09:00)."},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes (default 60)."},
                    "description": {"type": "string", "description": "Optional event description."},
                },
                "required": ["title", "date"],
            },
            handler=calendar_server.add_event,
            requires_confirmation=True,
        ))

        self.register_tool(ToolDef(
            name="get_upcoming_events",
            description="Get all upcoming calendar events within the next N days.",
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to look ahead (default 7)."},
                },
            },
            handler=calendar_server.get_upcoming,
        ))

    def _register_email_tools(self):
        self.register_tool(ToolDef(
            name="check_inbox",
            description="Check your email inbox for recent messages.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max emails to return (default 10)."},
                    "unread_only": {"type": "boolean", "description": "Only show unread emails (default true)."},
                },
            },
            handler=email_server.check_inbox,
        ))

        self.register_tool(ToolDef(
            name="send_email",
            description="Send an email via SMTP. WARNING: This requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                },
                "required": ["to", "subject", "body"],
            },
            handler=email_server.send_email,
            requires_confirmation=True,
        ))

    def _register_browser_tools(self):
        self.register_tool(ToolDef(
            name="open_web_page",
            description="Open and extract content from a web page. Use for research, reading articles, checking info.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to open."},
                },
                "required": ["url"],
            },
            handler=browser_server.open_page,
        ))

        self.register_tool(ToolDef(
            name="search_and_extract",
            description="Search the web and extract text content from results. Combines search + fetch in one step.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "site": {"type": "string", "description": "Optional: restrict search to a specific site."},
                },
                "required": ["query"],
            },
            handler=browser_server.search_and_extract,
        ))

    def _register_clipboard_ocr_tools(self):
        self.register_tool(ToolDef(
            name="get_clipboard",
            description="Get the current text content from your clipboard.",
            parameters={"type": "object", "properties": {}},
            handler=clipboard_ocr_server.get_clipboard_text,
        ))

        self.register_tool(ToolDef(
            name="ocr_image",
            description="Extract text from an image file using OCR. Useful for reading screenshots, scanned documents, photos of text.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the image file to OCR."},
                },
                "required": ["path"],
            },
            handler=clipboard_ocr_server.ocr_file,
        ))

    def _register_shell_tools(self):
        self.register_tool(ToolDef(
            name="shell_exec",
            description="Execute a whitelisted shell command. WARNING: Dangerous commands are automatically blocked. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."},
                    "cwd": {"type": "string", "description": "Working directory for the command."},
                },
                "required": ["command"],
            },
            handler=shell_server.execute,
            requires_confirmation=True,
        ))

    def _register_git_tools(self):
        self.register_tool(ToolDef(
            name="git_status",
            description="Get the current git status of a repository (modified files, branch info).",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Path to the git repository (default: current directory)."},
                },
            },
            handler=git_server.status,
        ))

        self.register_tool(ToolDef(
            name="git_log",
            description="Get recent git commit history for a repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Path to the git repository."},
                    "max_count": {"type": "integer", "description": "Max commits to show (default 10)."},
                },
            },
            handler=git_server.log,
        ))

        self.register_tool(ToolDef(
            name="git_diff",
            description="Get the current working tree diff (unstaged changes) for a repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Path to the git repository."},
                    "staged": {"type": "boolean", "description": "Show staged changes instead of unstaged (default false)."},
                },
            },
            handler=git_server.diff,
        ))

    def _register_telegram_tools(self):
        async def handle_send_message(text: str, parse_mode: str = "Markdown") -> str:
            return await telegram_bot_server.send_message(text, parse_mode)

        self.register_tool(ToolDef(
            name="telegram_send",
            description="Send a message via Telegram Bot. WARNING: This requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message text to send (max 4000 chars)."},
                    "parse_mode": {"type": "string", "description": "Message format: 'Markdown' or 'HTML'."},
                },
                "required": ["text"],
            },
            handler=handle_send_message,
            is_async=True,
            requires_confirmation=True,
        ))

        async def handle_get_updates(limit: int = 5) -> str:
            return await telegram_bot_server.get_updates(limit)

        self.register_tool(ToolDef(
            name="telegram_updates",
            description="Get recent messages sent to your Telegram Bot.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages to fetch (default 5)."},
                },
            },
            handler=handle_get_updates,
            is_async=True,
        ))

    def _load_external_servers(self) -> None:
        """Load tools from mcp_config.json external_servers section."""
        import os
        from pathlib import Path

        config_path = os.getenv("MCP_CONFIG_PATH", "")
        if not config_path or not Path(config_path).is_file():
            from app.config import settings
            config_path = settings.mcp_config_path
        path = Path(config_path)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        for server in data.get("external_servers", []):
            if not server.get("enabled", True):
                continue
            for tool_def in server.get("tools", []):
                name = tool_def.get("name")
                if not name:
                    continue

                def _make_handler(tname: str, response_template: str):
                    def handler(**kwargs) -> str:
                        return json.dumps({
                            "tool": tname,
                            "server": server.get("name", "external"),
                            "args": kwargs,
                            "result": response_template,
                        })
                    return handler

                template = tool_def.get("mock_response", f"External tool {name} executed")
                self.register_tool(ToolDef(
                    name=name,
                    description=tool_def.get("description", f"External MCP tool: {name}"),
                    parameters=tool_def.get("parameters", {"type": "object", "properties": {}}),
                    handler=_make_handler(name, template),
                    is_async=False,
                    requires_confirmation=tool_def.get("requires_confirmation", False),
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

        start_time = time.time()
        try:
            if tool.is_async:
                result = await tool.handler(**arguments)
            else:
                result = tool.handler(**arguments)

            latency = (time.time() - start_time) * 1000
            telemetry.record_tool_call(ToolCallRecord(
                tool_name=name,
                success=True,
                latency_ms=latency,
            ))

            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + "\n... [output truncated]"
            return result
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            telemetry.record_tool_call(ToolCallRecord(
                tool_name=name,
                success=False,
                latency_ms=latency,
                error_message=str(e),
            ))
            return json.dumps({"error": str(e)})


# Global singleton
mcp_hub = MCPHub()

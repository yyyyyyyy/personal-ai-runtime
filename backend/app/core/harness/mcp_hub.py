"""MCP Client Hub — manages tool registration, discovery, and invocation.

Supports both sync and async tool handlers. Adds web search, fetch, and
enhanced filesystem tools backed by dedicated server modules.
"""

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from app.core.harness.builtin_tools.browser import browser_server
from app.core.harness.builtin_tools.calendar import calendar_server
from app.core.harness.builtin_tools.email import email_server
from app.core.harness.builtin_tools.fetch import fetch_server
from app.core.harness.builtin_tools.filesystem import filesystem_server
from app.core.harness.builtin_tools.git import git_server
from app.core.harness.builtin_tools.goals import goals_server
from app.core.harness.builtin_tools.shell import shell_server
from app.core.harness.builtin_tools.telegram_bot import telegram_bot_server
from app.core.harness.builtin_tools.web_search import web_search_server
from app.core.telemetry.telemetry import ToolCallRecord, telemetry


@dataclass
class ToolDef:
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict
    handler: Callable[..., str | Awaitable[str]]
    is_async: bool = False
    requires_confirmation: bool = False


class MCPHub:
    """Central hub for managing tools and routing LLM tool calls."""

    # Categories registered by default — the lean core that every chat turn
    # sees. Keeping this small saves prompt tokens and shrinks the attack
    # surface (write-class tools visible to the model).
    CORE_CATEGORIES: frozenset[str] = frozenset({
        "time", "filesystem", "web", "calendar", "email", "browser",
        "shell", "git", "telegram", "goals",
    })
    # Advanced categories that depend on host GUI/hardware and are therefore
    # opt-in via settings.builtin_tool_categories.
    ADVANCED_CATEGORIES: frozenset[str] = frozenset({
        "computer_use", "voice", "clipboard_ocr",
    })

    def __init__(self, enabled_categories: set[str] | None = None):
        self._tools: dict[str, ToolDef] = {}
        if enabled_categories is None:
            try:
                from app.config import settings
                raw = settings.builtin_tool_categories.strip()
            except Exception:
                raw = ""
            if raw:
                enabled_categories = {c.strip() for c in raw.split(",") if c.strip()}
            else:
                enabled_categories = set(self.CORE_CATEGORIES)
        self._enabled_categories = enabled_categories
        self._register_all_tools()

    def _register_all_tools(self):
        # Core categories — always registered when present in the enabled set.
        if "time" in self._enabled_categories:
            self._register_time_tools()
        if "filesystem" in self._enabled_categories:
            self._register_filesystem_tools()
        if "web" in self._enabled_categories:
            self._register_web_tools()
        if "calendar" in self._enabled_categories:
            self._register_calendar_tools()
        if "email" in self._enabled_categories:
            self._register_email_tools()
        if "browser" in self._enabled_categories:
            self._register_browser_tools()
        if "shell" in self._enabled_categories:
            self._register_shell_tools()
        if "git" in self._enabled_categories:
            self._register_git_tools()
        if "telegram" in self._enabled_categories:
            self._register_telegram_tools()
        if "goals" in self._enabled_categories:
            self._register_goals_tools()
        # Advanced categories — opt-in only.
        if "clipboard_ocr" in self._enabled_categories:
            self._register_clipboard_ocr_tools()
        if "computer_use" in self._enabled_categories:
            self._register_computer_use_tools()
        if "voice" in self._enabled_categories:
            self._register_voice_tools()

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
            name="apply_patch",
            description=(
                "Apply a search-replace patch to a text file. "
                "Prefer this over write_file for small edits. Requires user confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to patch."},
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to find in the file (must be unique unless replace_all).",
                    },
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences (default false).",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            handler=filesystem_server.apply_patch,
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
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only show unread emails (default false). Set true for 未读邮件 only.",
                    },
                },
            },
            handler=email_server.check_inbox,
        ))

        self.register_tool(ToolDef(
            name="read_inbox_email",
            description=(
                "Read the full content of one email by position. "
                "Index 1 = newest. Use when user asks for 第N封, 下一封, or 继续 reading emails."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "1-based position (1=newest). Default 1.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many recent emails to search within (default 30).",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only search unread (default false).",
                    },
                },
            },
            handler=email_server.read_inbox_email,
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
            is_async=True,
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
            is_async=True,
        ))

    def _register_clipboard_ocr_tools(self):
        from app.core.harness.builtin_tools.clipboard_ocr import clipboard_ocr_server

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

    def _register_goals_tools(self):
        self.register_tool(ToolDef(
            name="create_goal",
            description="Create a new goal for the user. Use this when the user expresses an intention to achieve something.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Goal title (e.g. \"学习 Rust\")"},
                    "description": {"type": "string", "description": "Optional description"},
                    "importance": {"type": "number", "description": "Priority 0.0-1.0, default 0.5"},
                    "deadline": {"type": "string", "description": "Optional deadline (ISO date)"},
                },
                "required": ["title"],
            },
            handler=goals_server.create_goal,
        ))

        self.register_tool(ToolDef(
            name="update_goal_progress",
            description="Update a goal's progress. Use this when the user reports progress on a goal.",
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "The goal ID"},
                    "progress": {"type": "number", "description": "Progress 0.0 to 1.0"},
                    "note": {"type": "string", "description": "Optional note about this progress"},
                },
                "required": ["goal_id", "progress"],
            },
            handler=goals_server.update_progress,
        ))

        self.register_tool(ToolDef(
            name="complete_goal",
            description="Mark a goal as completed. Use this when the user finishes a goal.",
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "The goal ID"},
                    "reflection": {"type": "string", "description": "Optional reflection on what was learned"},
                },
                "required": ["goal_id"],
            },
            handler=goals_server.complete_goal,
        ))

        self.register_tool(ToolDef(
            name="list_active_goals",
            description="List the user's active goals with their current progress.",
            parameters={"type": "object", "properties": {}},
            handler=goals_server.list_active_goals,
        ))

    def register_mesh_tools(self, discovered: list) -> int:
        """Register tools discovered from external MCP servers."""
        from app.core.harness.mcp_mesh import mcp_mesh
        from app.core.runtime.capability_governance import capability_governance
        from app.core.runtime.taint import (
            register_external_ingestion_tool,
            register_external_write_tool,
        )

        count = 0
        for item in discovered:
            registered_name = item.registered_name

            async def _handler(_name: str = registered_name, **kwargs) -> str:
                return await mcp_mesh.call_tool(_name, kwargs)

            self.register_tool(ToolDef(
                name=registered_name,
                description=item.description,
                parameters=item.parameters,
                handler=_handler,
                is_async=True,
                requires_confirmation=item.requires_confirmation,
            ))
            capability_governance.register_external_tool(
                registered_name,
                risk=item.policy_risk,
            )
            if item.is_ingestion:
                register_external_ingestion_tool(registered_name)
            if item.requires_confirmation:
                register_external_write_tool(registered_name)
            count += 1
        return count

    def _register_computer_use_tools(self):
        from app.core.harness.builtin_tools.computer_use import computer_use_server

        self.register_tool(ToolDef(
            name="computer_screenshot",
            description="Take a screenshot of the entire screen or primary monitor. Returns base64-encoded PNG image with dimensions.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "enum": ["full", "primary"]},
                },
            },
            handler=lambda **kw: computer_use_server.screenshot(kw.get("region", "full")),
            requires_confirmation=False,
        ))
        self.register_tool(ToolDef(
            name="computer_click",
            description="Click at screen coordinates (x, y). Use computer_screenshot first.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                },
                "required": ["x", "y"],
            },
            handler=lambda **kw: computer_use_server.click(int(kw["x"]), int(kw["y"]), str(kw.get("button", "left"))),
            requires_confirmation=True,
        ))
        self.register_tool(ToolDef(
            name="computer_type",
            description="Type text at the current cursor position.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {"type": "number"},
                },
                "required": ["text"],
            },
            handler=lambda **kw: computer_use_server.type_text(str(kw["text"]), float(kw.get("interval", 0.05))),
            requires_confirmation=True,
        ))
        self.register_tool(ToolDef(
            name="computer_move",
            description="Move mouse to coordinates without clicking.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number"},
                },
                "required": ["x", "y"],
            },
            handler=lambda **kw: computer_use_server.move(int(kw["x"]), int(kw["y"]), float(kw.get("duration", 0.3))),
            requires_confirmation=False,
        ))
        self.register_tool(ToolDef(
            name="computer_scroll",
            description="Scroll the mouse wheel. Positive=up, negative=down.",
            parameters={
                "type": "object",
                "properties": {"clicks": {"type": "integer"}},
            },
            handler=lambda **kw: computer_use_server.scroll(int(kw.get("clicks", 3))),
            requires_confirmation=False,
        ))
        self.register_tool(ToolDef(
            name="computer_key",
            description="Press a keyboard key or shortcut (e.g. enter, ctrl+c).",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            handler=lambda **kw: computer_use_server.press_key(str(kw["key"])),
            requires_confirmation=True,
        ))
        self.register_tool(ToolDef(
            name="computer_screen_size",
            description="Get current screen resolution (width x height).",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kw: computer_use_server.screen_size(),
            requires_confirmation=False,
        ))

    def _register_voice_tools(self):
        from app.core.harness.builtin_tools.voice import voice_server

        self.register_tool(ToolDef(
            name="voice_tts",
            description="Convert text to speech. Generate an audio file from text that can be played back. Use when the user asks to hear something or speak text aloud.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to speak aloud"},
                    "voice": {
                        "type": "string",
                        "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                        "description": "Voice style to use",
                    },
                },
                "required": ["text"],
            },
            handler=lambda **kw: voice_server.tts(str(kw["text"]), str(kw.get("voice", "alloy"))),
            requires_confirmation=False,
        ))
        self.register_tool(ToolDef(
            name="voice_stt",
            description="Transcribe speech audio to text. Convert an audio recording into written text.",
            parameters={
                "type": "object",
                "properties": {
                    "audio_base64": {"type": "string", "description": "Base64-encoded audio bytes"},
                    "language": {"type": "string", "description": "Language code (zh, en, ja)"},
                },
                "required": ["audio_base64"],
            },
            handler=lambda **kw: voice_server.stt(str(kw["audio_base64"]), str(kw.get("language", "zh"))),
            requires_confirmation=False,
        ))

    def register_tool(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name, None)

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
                result = await cast(Awaitable[str], tool.handler(**arguments))
            else:
                result = cast(str, tool.handler(**arguments))

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

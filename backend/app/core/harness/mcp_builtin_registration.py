"""Builtin tool registration for MCPHub.

Extracted from ``mcp_hub.py`` so the God Object LOC budget (which counts only
``mcp_hub.py``) can shrink. Tools are declared as ``BuiltinToolSpec`` tables
per category and registered in a single loop.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.harness.builtin_tools.calendar import calendar_server
from app.core.harness.builtin_tools.email import email_server
from app.core.harness.builtin_tools.fetch import fetch_server
from app.core.harness.builtin_tools.filesystem import filesystem_server
from app.core.harness.builtin_tools.git import git_server
from app.core.harness.builtin_tools.goals import (
    _writer_complete_goal,
    _writer_create_goal,
    _writer_delete_goal,
    _writer_update_goal_progress,
    goals_server,
)
from app.core.harness.builtin_tools.shell import shell_server
from app.core.harness.builtin_tools.timer import _writer_set_timer
from app.core.harness.builtin_tools.web_search import web_search_server
from app.core.harness.mcp_hub import ToolDef


@dataclass(frozen=True)
class BuiltinToolSpec:
    """Declarative builtin tool — registered via ``_register_specs``."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    is_async: bool = False
    requires_confirmation: bool = False
    # Wrap sync handlers with ``asyncio.to_thread`` (implies ``is_async=True``).
    offload: bool = False


def _offload(fn: Callable[..., str]) -> Callable[..., object]:
    """Run a sync tool handler in a worker thread so it won't block the event loop.

    The wrapper keeps ``__signature__`` from ``fn`` so ``MCPHub`` kwargs
    filtering still drops unexpected LLM arguments.
    """

    @functools.wraps(fn)
    async def _handler(*args: object, **kwargs: object) -> str:
        return await asyncio.to_thread(fn, *args, **kwargs)

    try:
        _handler.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        pass
    return _handler


def _register_specs(hub, specs: Sequence[BuiltinToolSpec]) -> None:
    for spec in specs:
        handler = _offload(spec.handler) if spec.offload else spec.handler
        hub.register_tool(ToolDef(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            handler=handler,
            is_async=spec.is_async or spec.offload,
            requires_confirmation=spec.requires_confirmation,
        ))


def _register_all_tools(hub) -> None:
    for category, builder in _CATEGORY_BUILDERS.items():
        if category in hub._enabled_categories:
            _register_specs(hub, builder())


# ---------------------------------------------------------------------------
# Category builders (return tool tables)
# ---------------------------------------------------------------------------

def _time_specs() -> list[BuiltinToolSpec]:
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

    return [
        BuiltinToolSpec(
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
        ),
        BuiltinToolSpec(
            name="set_timer",
            description="Set a one-time reminder after a specified delay in minutes/hours.",
            parameters={
                "type": "object",
                "properties": {
                    "minutes": {"type": "number", "description": "Minutes to wait before firing."},
                    "hours": {"type": "number", "description": "Hours to wait before firing."},
                    "message": {"type": "string", "description": "The reminder message to show."},
                },
                "required": ["message"],
            },
            handler=_writer_set_timer,
        ),
    ]


def _filesystem_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="read_file",
            description="Read the contents of a text file. Returns the file content as plain text.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to read."},
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (default 500).",
                    },
                },
                "required": ["path"],
            },
            handler=filesystem_server.read_file,
            offload=True,
        ),
        BuiltinToolSpec(
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
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
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
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="list_directory",
            description="List files and subdirectories at a given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the directory to list.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter results (e.g. '*.md').",
                    },
                },
                "required": ["path"],
            },
            handler=filesystem_server.list_directory,
            offload=True,
        ),
        BuiltinToolSpec(
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
            offload=True,
        ),
    ]


def _web_specs() -> list[BuiltinToolSpec]:
    async def handle_web_search(query: str, max_results: int = 5) -> str:
        return await web_search_server.search(query, max_results)

    async def handle_fetch_url(url: str, extract_text: bool = True) -> str:
        return await fetch_server.fetch_url(url, extract_text)

    return [
        BuiltinToolSpec(
            name="web_search",
            description=(
                "Search the web for information. Use this when you need current "
                "information or facts you're unsure about."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default 5).",
                    },
                },
                "required": ["query"],
            },
            handler=handle_web_search,
            is_async=True,
        ),
        BuiltinToolSpec(
            name="fetch_url",
            description=(
                "Fetch and extract content from a web page URL. "
                "Returns the page title and readable text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch."},
                    "extract_text": {
                        "type": "boolean",
                        "description": "If true, extract readable text. If false, return raw HTML.",
                    },
                },
                "required": ["url"],
            },
            handler=handle_fetch_url,
            is_async=True,
        ),
    ]


def _calendar_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="list_calendar_events",
            description="List calendar events for a date range. Check what's happening on specific days.",
            parameters={
                "type": "object",
                "properties": {
                    "calendar": {
                        "type": "string",
                        "description": "Calendar name (default: 'default').",
                    },
                    "date": {"type": "string", "description": "Start date in YYYY-MM-DD format."},
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 7).",
                    },
                },
            },
            handler=calendar_server.list_events,
            offload=True,
        ),
        BuiltinToolSpec(
            name="add_calendar_event",
            description="Add an event to your calendar. Requires user confirmation for scheduling.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "date": {"type": "string", "description": "Event date in YYYY-MM-DD format."},
                    "time": {
                        "type": "string",
                        "description": "Event time in HH:MM format (default 09:00).",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (default 60).",
                    },
                    "description": {"type": "string", "description": "Optional event description."},
                    "location": {"type": "string", "description": "Optional event location."},
                },
                "required": ["title", "date"],
            },
            handler=calendar_server.add_event,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="get_upcoming_events",
            description="Get all upcoming calendar events within the next N days.",
            parameters={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 7).",
                    },
                },
            },
            handler=calendar_server.get_upcoming,
            offload=True,
        ),
    ]


def _email_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="check_inbox",
            description="Check your email inbox for recent messages.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max emails to return (default 10).",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only show unread emails (default false). Set true for 未读邮件 only.",
                    },
                },
            },
            handler=email_server.check_inbox,
            offload=True,
        ),
        BuiltinToolSpec(
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
            offload=True,
        ),
        BuiltinToolSpec(
            name="mark_inbox_email_read",
            description=(
                "Mark one inbox email as read (IMAP). "
                "Use when the user asks to 标记已读 / mark as read. "
                "Prefer message_id from check_inbox/read_inbox_email; else use index (1=newest)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Stable Message-ID from check_inbox/read_inbox_email.",
                    },
                    "index": {
                        "type": "integer",
                        "description": "1-based position among recent mail (1=newest).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Listing window size (default 30).",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Search unread list only (default true for mark-read).",
                    },
                },
            },
            handler=email_server.mark_inbox_email_read,
            offload=True,
        ),
        BuiltinToolSpec(
            name="mark_inbox_email_unread",
            description=(
                "Mark one inbox email as unread (IMAP). "
                "Use when the user asks to 标记未读 / mark as unread. "
                "Prefer message_id from check_inbox/read_inbox_email; else use index (1=newest)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Stable Message-ID from check_inbox/read_inbox_email.",
                    },
                    "index": {
                        "type": "integer",
                        "description": "1-based position among recent mail (1=newest).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Listing window size (default 30).",
                    },
                },
            },
            handler=email_server.mark_inbox_email_unread,
            offload=True,
        ),
        BuiltinToolSpec(
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
            offload=True,
            requires_confirmation=True,
        ),
    ]


def _shell_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="shell_exec",
            description=(
                "Execute a whitelisted shell command. WARNING: Dangerous commands "
                "are automatically blocked. Requires confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."},
                    "cwd": {"type": "string", "description": "Working directory for the command."},
                },
                "required": ["command"],
            },
            handler=shell_server.execute,
            offload=True,
            requires_confirmation=True,
        ),
    ]


def _git_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="git_status",
            description="Get the current git status of a repository (modified files, branch info).",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the git repository (default: current directory).",
                    },
                },
            },
            handler=git_server.status,
            offload=True,
        ),
        BuiltinToolSpec(
            name="git_log",
            description="Get recent git commit history for a repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Path to the git repository."},
                    "max_count": {
                        "type": "integer",
                        "description": "Max commits to show (default 10).",
                    },
                },
            },
            handler=git_server.log,
            offload=True,
        ),
        BuiltinToolSpec(
            name="git_diff",
            description="Get the current working tree diff (unstaged changes) for a repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Path to the git repository."},
                    "staged": {
                        "type": "boolean",
                        "description": "Show staged changes instead of unstaged (default false).",
                    },
                },
            },
            handler=git_server.diff,
            offload=True,
        ),
    ]


def _goals_specs() -> list[BuiltinToolSpec]:
    return [
        BuiltinToolSpec(
            name="create_goal",
            description=(
                "Create a new goal for the user. Use this when the user expresses "
                "an intention to achieve something."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Goal title (e.g. \"学习 Rust\")"},
                    "description": {"type": "string", "description": "Optional description"},
                    "importance": {
                        "type": "number",
                        "description": "Priority 0.0-1.0, default 0.5",
                    },
                    "deadline": {"type": "string", "description": "Optional deadline (ISO date)"},
                },
                "required": ["title"],
            },
            handler=_writer_create_goal,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
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
            handler=_writer_update_goal_progress,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="complete_goal",
            description="Mark a goal as completed. Use this when the user finishes a goal.",
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "The goal ID"},
                    "reflection": {
                        "type": "string",
                        "description": "Optional reflection on what was learned",
                    },
                },
                "required": ["goal_id"],
            },
            handler=_writer_complete_goal,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="delete_goal",
            description=(
                "Delete a goal and all its child actions. "
                "Use when the user asks to delete or remove a goal."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "The goal ID to delete"},
                },
                "required": ["goal_id"],
            },
            handler=_writer_delete_goal,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="list_active_goals",
            description="List the user's active goals with their current progress.",
            parameters={"type": "object", "properties": {}},
            handler=goals_server.list_active_goals,
        ),
    ]


def _telegram_specs() -> list[BuiltinToolSpec]:
    from app.core.harness.builtin_tools.telegram_bot import telegram_bot_server

    async def handle_send_message(text: str, parse_mode: str = "Markdown") -> str:
        return await telegram_bot_server.send_message(text, parse_mode)

    async def handle_get_updates(limit: int = 5) -> str:
        return await telegram_bot_server.get_updates(limit)

    return [
        BuiltinToolSpec(
            name="telegram_send",
            description="Send a message via Telegram Bot. WARNING: This requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Message text to send (max 4000 chars).",
                    },
                    "parse_mode": {
                        "type": "string",
                        "description": "Message format: 'Markdown' or 'HTML'.",
                    },
                },
                "required": ["text"],
            },
            handler=handle_send_message,
            is_async=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="telegram_updates",
            description="Get recent messages sent to your Telegram Bot.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to fetch (default 5).",
                    },
                },
            },
            handler=handle_get_updates,
            is_async=True,
        ),
    ]


def _clipboard_ocr_specs() -> list[BuiltinToolSpec]:
    from app.core.harness.builtin_tools.clipboard_ocr import clipboard_ocr_server

    return [
        BuiltinToolSpec(
            name="get_clipboard",
            description="Get the current text content from your clipboard.",
            parameters={"type": "object", "properties": {}},
            handler=clipboard_ocr_server.get_clipboard_text,
            offload=True,
        ),
        BuiltinToolSpec(
            name="ocr_image",
            description=(
                "Extract text from an image file using OCR. Useful for reading "
                "screenshots, scanned documents, photos of text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the image file to OCR."},
                },
                "required": ["path"],
            },
            handler=clipboard_ocr_server.ocr_file,
            offload=True,
        ),
    ]


def _computer_use_specs() -> list[BuiltinToolSpec]:
    from app.core.harness.builtin_tools.computer_use import computer_use_server

    def _screenshot(region: str = "full") -> str:
        return computer_use_server.screenshot(region)

    def _click(x: int, y: int, button: str = "left") -> str:
        return computer_use_server.click(int(x), int(y), str(button))

    def _type_text(text: str, interval: float = 0.05) -> str:
        return computer_use_server.type_text(str(text), float(interval))

    def _move(x: int, y: int, duration: float = 0.3) -> str:
        return computer_use_server.move(int(x), int(y), float(duration))

    def _scroll(clicks: int = 3) -> str:
        return computer_use_server.scroll(int(clicks))

    def _press_key(key: str) -> str:
        return computer_use_server.press_key(str(key))

    def _screen_size() -> str:
        return computer_use_server.screen_size()

    return [
        BuiltinToolSpec(
            name="computer_screenshot",
            description=(
                "Take a screenshot of the entire screen or primary monitor. "
                "Returns base64-encoded PNG image with dimensions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "enum": ["full", "primary"]},
                },
            },
            handler=_screenshot,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
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
            handler=_click,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="computer_type",
            description="Type text at the current cursor position (Unicode/CJK via clipboard paste).",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {"type": "number"},
                },
                "required": ["text"],
            },
            handler=_type_text,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
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
            handler=_move,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="computer_scroll",
            description="Scroll the mouse wheel. Positive=up, negative=down.",
            parameters={
                "type": "object",
                "properties": {"clicks": {"type": "integer"}},
            },
            handler=_scroll,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="computer_key",
            description="Press a keyboard key or shortcut (e.g. enter, ctrl+c).",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            handler=_press_key,
            offload=True,
            requires_confirmation=True,
        ),
        BuiltinToolSpec(
            name="computer_screen_size",
            description="Get current screen resolution (width x height).",
            parameters={"type": "object", "properties": {}},
            handler=_screen_size,
            offload=True,
        ),
    ]


def _voice_specs() -> list[BuiltinToolSpec]:
    from app.core.harness.builtin_tools.voice import voice_server

    async def handle_tts(text: str, voice: str = "alloy") -> str:
        return await voice_server.tts(text, voice)

    async def handle_stt(audio_base64: str, language: str = "zh") -> str:
        return await voice_server.stt(audio_base64, language)

    return [
        BuiltinToolSpec(
            name="voice_tts",
            description=(
                "Convert text to speech via a configured OpenAI-compatible audio API "
                "(requires VOICE_BASE_URL)."
            ),
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
            handler=handle_tts,
            is_async=True,
        ),
        BuiltinToolSpec(
            name="voice_stt",
            description=(
                "Transcribe speech audio to text via a configured OpenAI-compatible "
                "audio API (requires VOICE_BASE_URL)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "audio_base64": {
                        "type": "string",
                        "description": "Base64-encoded audio bytes",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (zh, en, ja)",
                    },
                },
                "required": ["audio_base64"],
            },
            handler=handle_stt,
            is_async=True,
        ),
    ]


_CATEGORY_BUILDERS: dict[str, Callable[[], list[BuiltinToolSpec]]] = {
    # Core
    "time": _time_specs,
    "filesystem": _filesystem_specs,
    "web": _web_specs,
    "calendar": _calendar_specs,
    "email": _email_specs,
    "shell": _shell_specs,
    "git": _git_specs,
    "goals": _goals_specs,
    # Advanced (opt-in)
    "telegram": _telegram_specs,
    "clipboard_ocr": _clipboard_ocr_specs,
    "computer_use": _computer_use_specs,
    "voice": _voice_specs,
}


def register_mesh_tools(hub, discovered: list) -> int:
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
        capability_governance.register_external_tool(
            registered_name,
            risk=item.policy_risk,
        )
        # Forbidden tools stay in governance (deny) but are not exposed to the
        # LLM schema or invokable via the hub handler table.
        if item.policy_risk == "forbidden":
            continue

        async def _handler(_name: str = registered_name, **kwargs) -> str:
            return await mcp_mesh.call_tool(_name, kwargs)

        hub.register_tool(ToolDef(
            name=registered_name,
            description=item.description,
            parameters=item.parameters,
            handler=_handler,
            is_async=True,
            requires_confirmation=item.requires_confirmation,
        ))
        if item.is_ingestion:
            register_external_ingestion_tool(registered_name)
        if item.requires_confirmation:
            register_external_write_tool(registered_name)
        count += 1
    return count

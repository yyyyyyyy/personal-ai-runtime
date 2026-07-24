"""Core category tool-spec builders (time, filesystem, web, shell, git)."""

from __future__ import annotations

import json

from app.core.harness.builtin_registration.common import BuiltinToolSpec
from app.core.harness.builtin_tools.fetch import fetch_server
from app.core.harness.builtin_tools.filesystem import filesystem_server
from app.core.harness.builtin_tools.git import git_server
from app.core.harness.builtin_tools.shell import shell_server
from app.core.harness.builtin_tools.timer import _writer_set_timer
from app.core.harness.builtin_tools.web_search import web_search_server


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

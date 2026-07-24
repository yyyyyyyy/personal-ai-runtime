"""Domain / advanced category tool-spec builders."""

from __future__ import annotations

from app.core.harness.builtin_registration.common import BuiltinToolSpec
from app.core.harness.builtin_tools.calendar import calendar_server
from app.core.harness.builtin_tools.email import email_server
from app.core.harness.builtin_tools.goals import (
    _writer_complete_goal,
    _writer_create_goal,
    _writer_delete_goal,
    _writer_update_goal_progress,
    goals_server,
)


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

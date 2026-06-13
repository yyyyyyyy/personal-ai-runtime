"""Filter and parse LLM tool-call markup leaked into text content.

Some providers (notably DeepSeek) occasionally emit markup like
<｜tool_calls><｜invoke name="shell_exec">…</｜invoke></｜tool_calls>
in delta.content instead of structured delta.tool_calls.
We strip it from the user-visible stream and optionally recover
executable tool calls.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

# Fullwidth ｜ (U+FF5C) and ASCII | both appear in provider output.
_PIPE = r"[｜|]+"

_OPEN = rf"{_PIPE}tool_calls"
_CLOSE = rf"{_PIPE}tool_calls"
_INVOKE = rf"{_PIPE}invoke"
_INVOKE_CLOSE = rf"{_PIPE}invoke"
_PARAM = rf"{_PIPE}parameter"

_TOOL_CALLS_BLOCK_RE = re.compile(
    rf"<\s*{_OPEN}\s*>.*?<\s*/\s*{_CLOSE}\s*>",
    re.DOTALL | re.IGNORECASE,
)
_INVOKE_BLOCK_RE = re.compile(
    rf"<\s*{_INVOKE}\s+name=\"([^\"]+)\"[^>]*>(.*?)<\s*/\s*{_INVOKE_CLOSE}\s*>",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_RE = re.compile(
    rf"<\s*{_PARAM}\s+name=\"([^\"]+)\"[^>]*>(.*?)<\s*/\s*{_PARAM}\s*>",
    re.DOTALL | re.IGNORECASE,
)
_ANY_TOOL_MARKUP_RE = re.compile(rf"<\s*{_OPEN}", re.IGNORECASE)


def has_tool_markup(text: str) -> bool:
    return bool(text and _ANY_TOOL_MARKUP_RE.search(text))


def strip_tool_markup(text: str) -> str:
    """Remove leaked tool-call markup from assistant text."""
    if not text:
        return ""
    cleaned = _TOOL_CALLS_BLOCK_RE.sub("", text)
    cleaned = _INVOKE_BLOCK_RE.sub("", cleaned)
    # Drop orphan opening tags still buffering
    cleaned = re.sub(rf"<\s*{_OPEN}\s*>[\s\S]*", "", cleaned)
    return cleaned.strip()


def parse_tool_calls(text: str) -> tuple[list[dict[str, Any]], str]:
    """Parse leaked tool-call markup into Brain tool_calls_data shape."""
    if not has_tool_markup(text):
        return [], text

    calls: list[dict[str, Any]] = []
    for match in _INVOKE_BLOCK_RE.finditer(text):
        tool_name = match.group(1).strip()
        body = match.group(2)
        args: dict[str, Any] = {}
        for param in _PARAM_RE.finditer(body):
            key = param.group(1).strip()
            raw_val = param.group(2).strip()
            val: Any = raw_val
            if raw_val.lower() in ("true", "false"):
                val = raw_val.lower() == "true"
            args[key] = val
        calls.append({
            "index": len(calls),
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "function_name": tool_name,
            "arguments": json.dumps(args, ensure_ascii=False),
        })

    return calls, strip_tool_markup(text)

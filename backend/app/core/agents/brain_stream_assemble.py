"""Assemble streaming LLM chunks into visible text + tool calls.

Extracted from ``brain_chat_stream`` so markup recovery and tool-call
delta assembly can be unit-tested without the full chat loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.core.agents.tool_markup import parse_tool_calls, strip_tool_markup

logger = logging.getLogger(__name__)


@dataclass
class AssembledStream:
    """Final result of consuming one LLM stream response."""

    visible_text: str
    tool_calls: list[dict]
    usage: Any = None
    raw_text: str = ""


@dataclass
class _ToolCallBuilder:
    index: int = -1
    id: str = ""
    function_name: str = ""
    arguments: str = ""

    def as_dict(self) -> dict[str, int | str]:
        return {
            "index": self.index,
            "id": self.id,
            "function_name": self.function_name,
            "arguments": self.arguments,
        }


async def iter_assembled_stream(response) -> AsyncIterator[dict]:
    """Consume a streaming LLM response.

    Yields:
        ``{"type": "text_delta", "content": ...}`` for user-visible text.
        Final event ``{"type": "_stream_assembled", "result": AssembledStream}``.
    """
    raw_text = ""
    visible = ""
    tool_calls: list[dict] = []
    current = _ToolCallBuilder()
    usage: Any = None

    async for chunk in response:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        if delta.content:
            raw_text += delta.content
            cleaned = strip_tool_markup(raw_text)
            extra = cleaned[len(visible) :]
            if extra:
                visible = cleaned
                yield {"type": "text_delta", "content": extra}

        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.index is not None and tc.index != current.index:
                    if current.index >= 0:
                        tool_calls.append(current.as_dict())
                    current = _ToolCallBuilder(
                        index=tc.index,
                        id=tc.id or "",
                    )
                if tc.id:
                    current.id = tc.id
                if tc.function:
                    if tc.function.name:
                        current.function_name += tc.function.name
                    if tc.function.arguments:
                        current.arguments += tc.function.arguments

    if current.index >= 0:
        tool_calls.append(current.as_dict())

    if not tool_calls and raw_text:
        parsed, cleaned = parse_tool_calls(raw_text)
        if parsed:
            tool_calls = parsed
            visible = cleaned
            logger.info(
                "Recovered %d tool call(s) from markup in text stream",
                len(parsed),
            )

    yield {
        "type": "_stream_assembled",
        "result": AssembledStream(
            visible_text=visible,
            tool_calls=tool_calls,
            usage=usage,
            raw_text=raw_text,
        ),
    }

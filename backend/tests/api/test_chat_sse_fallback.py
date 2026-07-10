"""Tests for chat SSE queue draining and fallback behavior."""

import asyncio

from app.api.chat import _drain_sse_queue


def test_drain_sse_queue_returns_buffered_items_in_order():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    queue.put_nowait({"type": "tool_result", "tool_name": "check_inbox"})
    queue.put_nowait({"type": "text_delta", "content": "已加载最近 10 封邮件"})
    queue.put_nowait({"type": "done"})

    drained = _drain_sse_queue(queue)

    assert [item["type"] for item in drained] == ["tool_result", "text_delta", "done"]
    assert _drain_sse_queue(queue) == []


def test_drain_sse_queue_on_empty_queue():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    assert _drain_sse_queue(queue) == []

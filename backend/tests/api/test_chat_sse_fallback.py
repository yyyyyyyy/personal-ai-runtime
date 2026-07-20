"""Tests for chat SSE queue draining and fallback behavior.

``_drain_sse_queue`` is the non-blocking helper used when ChatDone arrives
while the stream loop is idle — it must return every buffered frame (in order)
so the fallback path does not skip pending text_delta / tool_result items.
"""

import asyncio

from app.api.chat import _drain_sse_queue, _yield_completion_extras


def test_drain_sse_queue_returns_buffered_items_in_order():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    queue.put_nowait({"type": "tool_result", "tool_name": "check_inbox"})
    queue.put_nowait({"type": "text_delta", "content": "已加载最近 10 封邮件"})
    queue.put_nowait({"type": "done"})

    drained = _drain_sse_queue(queue)

    assert [item["type"] for item in drained] == ["tool_result", "text_delta", "done"]
    assert drained[0]["tool_name"] == "check_inbox"
    assert drained[1]["content"] == "已加载最近 10 封邮件"
    assert _drain_sse_queue(queue) == []


def test_drain_sse_queue_on_empty_queue():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    assert _drain_sse_queue(queue) == []


def test_drain_sse_queue_preserves_unknown_and_empty_payloads():
    """Drain itself does not filter — the SSE loop decides what to yield."""
    queue: asyncio.Queue[dict] = asyncio.Queue()
    queue.put_nowait({"type": "text_delta", "content": ""})
    queue.put_nowait({"type": "ping"})
    queue.put_nowait({"type": "error", "content": "boom"})

    drained = _drain_sse_queue(queue)
    assert len(drained) == 3
    assert drained[0] == {"type": "text_delta", "content": ""}
    assert drained[1]["type"] == "ping"
    assert drained[2]["type"] == "error"


def test_drain_sse_queue_large_batch_empties_queue():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    for i in range(50):
        queue.put_nowait({"type": "text_delta", "content": str(i)})

    drained = _drain_sse_queue(queue)
    assert len(drained) == 50
    assert drained[0]["content"] == "0"
    assert drained[-1]["content"] == "49"
    assert queue.empty()


def test_yield_completion_extras_empty_without_sources_or_pending():
    assert _yield_completion_extras({}, "conv-empty") == []


def test_yield_completion_extras_emits_sources_and_confirmation():
    from app.core.runtime.governance.context_pipeline import _store_sources

    _store_sources("conv-1", [{"title": "doc", "url": "https://example.com"}])
    lines = _yield_completion_extras(
        {"pending": True, "approval_id": "apr_1", "tool_name": "write_file"},
        "conv-1",
    )
    assert len(lines) == 2
    assert "sources" in lines[0]
    assert "example.com" in lines[0]
    assert "confirmation_required" in lines[1]
    assert "apr_1" in lines[1]
    # get_sources is one-shot — second call should not re-emit
    assert _yield_completion_extras({"pending": False}, "conv-1") == []

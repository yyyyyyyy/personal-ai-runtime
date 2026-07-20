"""End-to-end SSE chat tests — direct handler invocation.

These tests call ``send_message`` directly (bypassing HTTP) and consume its
``StreamingResponse`` as SSE frames.  FakeBrain (from tests/conftest.py)
replaces the real Brain so no LLM is called.

Conversation setup uses the shared sync ``client``; streaming stays async
via ``_invoke_send_message``.
"""

import json
import os
from typing import Any

import pytest

os.environ.setdefault("LLM_API_KEY", "test-key")


# ── helpers ────────────────────────────────────────────────────────────


def _parse_sse_frames(lines: list[str]) -> list[dict[str, Any]]:
    """Extract and JSON-decode all ``data: {...}`` frames from response lines."""
    frames: list[dict[str, Any]] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("data: "):
            try:
                frames.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return frames


async def _invoke_send_message(conv_id: str, content: str) -> list[dict[str, Any]]:
    """Call the chat endpoint directly and collect SSE frames from the stream."""
    from app.api.chat import SendMessageRequest, send_message

    body = SendMessageRequest(content=content)
    response = await send_message(conv_id=conv_id, body=body)
    lines: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        for line in chunk.splitlines():
            lines.append(line)
    return _parse_sse_frames(lines)


def _create_conversation(client, title: str) -> str:
    conv = client.post("/api/chat/conversations", params={"title": title})
    assert conv.status_code == 200, conv.text
    return conv.json()["id"]


# ── tests ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_chat_sse_happy_path(fake_brain, client):
    """Normal chat: text_delta stream → done, ChatCompleted written to event_log."""
    from app.core.runtime.kernel_instance import kernel

    fake_brain.set_script([
        {"type": "text_delta", "content": "Hello "},
        {"type": "text_delta", "content": "world!"},
        {"type": "done"},
    ])

    conv_id = _create_conversation(client, "SSE E2E")
    frames = await _invoke_send_message(conv_id, "Hi there")

    types = [f.get("type") for f in frames]
    assert "text_delta" in types, f"Expected text_delta in frames, got {types}"
    assert types[-1] == "done", f"Expected done as last frame, got {types[-1]}"

    text = "".join(f.get("content", "") for f in frames if f.get("type") == "text_delta")
    assert "Hello " in text
    assert "world!" in text

    completed = kernel.read_events(
        type="ChatCompleted",
        aggregate_id=f"chat_{conv_id}",
        order="desc",
        limit=1,
    )
    assert len(completed) > 0, "ChatCompleted event not found in event_log"
    assert "Hello world!" in completed[0].payload.get("content", "")


@pytest.mark.anyio
async def test_chat_sse_error_path(fake_brain, client):
    """LLM failure → error frame → stream closes cleanly."""
    fake_brain.set_script([
        {"type": "error", "content": "LLM API error: rate limited"},
    ])

    conv_id = _create_conversation(client, "SSE Err")
    frames = await _invoke_send_message(conv_id, "trigger error")

    types = [f.get("type") for f in frames]
    assert "error" in types, f"Expected error frame, got {types}"
    assert types[-1] == "error", f"Expected error as last frame, got {types[-1]}"


@pytest.mark.anyio
async def test_chat_sse_tool_call_path(fake_brain, client):
    """Tool call: tool_call_start → tool_result → text_delta → done."""
    fake_brain.set_script([
        {"type": "tool_call_start", "tool_calls": [{"id": "tc1", "function": {"name": "get_current_time", "arguments": "{}"}}]},
        {"type": "tool_result", "tool_name": "get_current_time", "content": "12:00"},
        {"type": "text_delta", "content": "The time is 12:00"},
        {"type": "done"},
    ])

    conv_id = _create_conversation(client, "SSE Tool")
    frames = await _invoke_send_message(conv_id, "What time is it?")

    types = [f.get("type") for f in frames]
    assert "tool_call_start" in types, f"Expected tool_call_start, got {types}"
    assert "tool_result" in types, f"Expected tool_result, got {types}"
    assert types[-1] == "done"


@pytest.mark.anyio
async def test_chat_sse_confirmation_required_path(fake_brain, client):
    """Approval suspension: done.result carries pending=True + approval_id.

    ChatHandler does not push confirmation_required as a separate SSE frame;
    it folds the approval payload into ChatCompleted / the final done.result.
    """
    from app.core.runtime.kernel_instance import kernel

    fake_brain.set_script([
        {"type": "confirmation_required", "tool_name": "write_file",
         "tool_args": {"path": "/tmp/out.txt", "content": "data"},
         "tool_call_id": "tc1", "approval_id": "apr_test123"},
        {"type": "done"},
    ])

    conv_id = _create_conversation(client, "SSE Appr")
    frames = await _invoke_send_message(conv_id, "Write a file")

    types = [f.get("type") for f in frames]
    assert types[-1] == "done", f"Expected done as last frame, got {types}"

    done_frame = next(f for f in frames if f.get("type") == "done")
    result = done_frame.get("result") or {}
    assert result.get("pending") is True, f"Expected pending=True in done.result, got {result}"
    assert result.get("approval_id") == "apr_test123"
    assert result.get("tool_name") == "write_file"

    completed = kernel.read_events(
        type="ChatCompleted",
        aggregate_id=f"chat_{conv_id}",
        order="desc",
        limit=1,
    )
    assert len(completed) > 0
    assert completed[0].payload.get("pending") is True
    assert completed[0].payload.get("approval_id") == "apr_test123"

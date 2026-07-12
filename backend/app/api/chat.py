"""Chat API — conversation and message endpoints with SSE streaming."""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.models import ResolveApprovalRequest, SendMessageRequest
from app.config import settings
from app.core.agents.brain import Brain
from app.core.agents.conversation import ConversationAPI, ConversationManager
from app.core.agents.tool_markup import strip_tool_markup
from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["chat"])


def _drain_sse_queue(queue: asyncio.Queue) -> list[dict]:
    """Return all items currently buffered in the SSE queue (non-blocking)."""
    items: list[dict] = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


def _yield_completion_extras(result: dict, conv_id: str) -> list[str]:
    """Build SSE lines for sources and confirmation_required before done."""
    from app.core.runtime.governance.context_pipeline import get_sources

    lines: list[str] = []
    sources = get_sources(conv_id)
    if sources:
        lines.append(f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n")
    if result.get("pending"):
        lines.append(
            f"data: {json.dumps({'type': 'confirmation_required', 'tool_name': result.get('tool_name', ''), 'tool_args': result.get('tool_args', {}), 'tool_call_id': result.get('tool_call_id', ''), 'approval_id': result.get('approval_id', '')})}\n\n"
        )
    return lines


@router.post("/conversations")
async def create_conversation(title: str | None = None):
    """Create a new conversation."""
    conv = ConversationAPI.create(title=title)
    return conv


@router.get("/conversations")
async def list_conversations(limit: int = 50):
    """List all conversations."""
    return ConversationAPI.list_all(limit=limit)


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get a conversation by ID."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation and its messages."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ConversationAPI.delete(conv_id)
    return {"status": "ok"}


@router.patch("/conversations/{conv_id}")
async def update_conversation(conv_id: str, title: str | None = None):
    """Update conversation title."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ConversationAPI.update(conv_id, title=title)
    return {"status": "ok"}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, limit: int = 100):
    """Get messages for a conversation."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = read_ports.query_conversation_messages(
        conv_id, limit=limit, order="created_at_asc",
    )
    result = []
    for row in rows:
        item = dict(row)
        if item.get("role") == "assistant" and item.get("content"):
            item["content"] = strip_tool_markup(item["content"])
        # Parse sources if stored as JSON string
        if item.get("sources") and isinstance(item["sources"], str):
            try:
                item["sources"] = json.loads(item["sources"])
            except json.JSONDecodeError:
                item["sources"] = None
        result.append(item)
    return result


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: SendMessageRequest):
    """Send a message — emits ChatRequested, Scheduler processes via ChatHandler."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    content = body.content
    if not content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")

    import asyncio
    import json as _json
    import uuid

    correlation_id = f"chat_{uuid.uuid4().hex[:12]}"

    from app.core.runtime.agent_scheduler import ensure_scheduler
    await ensure_scheduler(kernel)

    from app.core.runtime.agent_scheduler import get_scheduler
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    from app.core.runtime.notification_bridge import register, unregister
    sse_queue = register(correlation_id)

    kernel.emit_event(
        "ChatRequested",
        "chat",
        conv_id,  # aggregate_id = conversation dimension, not per-message UUID
        payload={
            "user_message": content,
            "conversation_id": conv_id,
        },
        actor="user",
        correlation_id=correlation_id,
    )

    async def sse_stream():
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + settings.total_tool_loop_timeout + 10.0
            last_ping = loop.time()
            while loop.time() < deadline:
                # Read text deltas from the in-memory queue (no event_log writes)
                try:
                    item = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Send heartbeat ping every 15s to prevent proxy timeouts
                    now = loop.time()
                    if now - last_ping >= 15.0:
                        yield f"data: {_json.dumps({'type': 'ping'})}\n\n"
                        last_ping = now

                    # Fallback only when the queue is idle — avoids racing past
                    # pending text_delta/tool_result items still in the queue.
                    done = kernel.read_events(correlation_id=correlation_id, type="ChatDone")
                    if not done:
                        continue

                    streamed_text = False
                    for pending in _drain_sse_queue(sse_queue):
                        if pending.get("type") == "text_delta" and pending.get("content"):
                            streamed_text = True
                            yield f"data: {_json.dumps(pending)}\n\n"
                        elif pending.get("type") in ("tool_call_start", "tool_result"):
                            yield f"data: {_json.dumps(pending)}\n\n"
                        elif pending.get("type") == "done":
                            if pending.get("result"):
                                for line in _yield_completion_extras(pending["result"], conv_id):
                                    yield line
                            yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                            return
                        elif pending.get("type") == "error":
                            yield f"data: {_json.dumps({'type': 'error', 'content': pending.get('content', '')})}\n\n"
                            return

                    completed = kernel.read_events(correlation_id=correlation_id, type="ChatCompleted")
                    if completed:
                        result = completed[0].payload
                        content = result.get("content", "")
                        if content and not streamed_text:
                            yield f"data: {_json.dumps({'type': 'text_delta', 'content': content})}\n\n"
                        for line in _yield_completion_extras(result, conv_id):
                            yield line
                        yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                    return
                else:
                    if item.get("type") == "text_delta" and item.get("content"):
                        yield f"data: {_json.dumps(item)}\n\n"
                    elif item.get("type") in ("tool_call_start", "tool_result"):
                        yield f"data: {_json.dumps(item)}\n\n"
                    elif item.get("type") == "done":
                        if item.get("result"):
                            for line in _yield_completion_extras(item["result"], conv_id):
                                yield line
                        yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                        return
                    elif item.get("type") == "error":
                        yield f"data: {_json.dumps({'type': 'error', 'content': item.get('content', '')})}\n\n"
                        return

            yield f"data: {_json.dumps({'type': 'error', 'content': 'Chat request timed out'})}\n\n"
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning("SSE stream error for %s: %s", correlation_id, exc, exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'content': 'An internal error occurred. Please try again.'})}\n\n"
        finally:
            unregister(correlation_id)

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _load_pending_approval(approval_id: str) -> tuple[str, dict]:
    """Load action/params from the governed approval projection (authoritative)."""
    approval = read_ports.query_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval already {approval['status']}",
        )
    tool_name = approval.get("action") or ""
    if not tool_name:
        raise HTTPException(status_code=400, detail="Approval record missing action")
    raw_params = approval.get("params") or "{}"
    try:
        tool_args = json.loads(raw_params) if isinstance(raw_params, str) else dict(raw_params)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Approval record has invalid params") from None
    return tool_name, tool_args


async def _resume_conversation_after_approval(
    conv_id: str,
    tool_call_id: str,
    result_str: str,
) -> str | None:
    """Persist tool result and continue the chat turn when conversation context is present."""
    if not conv_id or not tool_call_id:
        return None
    conversation = ConversationManager(conversation_id=conv_id)
    conversation.save_tool_result(result_str, tool_call_id)
    brain = Brain()
    return await brain.continue_after_tool_result(conversation)


def _reject_client_approval_mismatch(body: ResolveApprovalRequest, tool_name: str, tool_args: dict) -> None:
    """Reject if the client payload disagrees with the immutable approval record."""
    if body.tool_name and body.tool_name != tool_name:
        raise HTTPException(status_code=400, detail="tool_name does not match approval record")
    if body.tool_args and body.tool_args != tool_args:
        raise HTTPException(status_code=400, detail="tool_args do not match approval record")


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, body: ResolveApprovalRequest):
    """Resolve a pending approval — submit_command for synchronous request-response."""

    tool_name, tool_args = _load_pending_approval(approval_id)
    _reject_client_approval_mismatch(body, tool_name, tool_args)

    from app.core.runtime.agent_scheduler import ensure_scheduler
    await ensure_scheduler(kernel)
    from app.core.runtime.agent_scheduler import get_scheduler
    scheduler = get_scheduler(kernel)
    await scheduler.start()

    result = await kernel.submit_command(
        "ApproveRequested",
        "approval",
        f"approve_{approval_id}",
        payload={
            "approval_id": approval_id,
            "decision": body.decision,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "conv_id": body.conv_id or "",
            "tool_call_id": body.tool_call_id or "",
        },
        actor="user",
        timeout=settings.submit_command_timeout_approval,
    )

    if result.get("error") == "timeout":
        raise HTTPException(status_code=504, detail="Approval resolution timed out")

    payload: dict = {"status": result.get("status", "error"), "result": result.get("result", "")}
    if result.get("assistant_message"):
        from app.core.agents.tool_markup import strip_tool_markup
        payload["assistant_message"] = strip_tool_markup(result["assistant_message"])
    return payload

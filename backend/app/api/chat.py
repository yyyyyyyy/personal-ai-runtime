"""Chat API — conversation and message endpoints with SSE streaming."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.agents.brain import Brain
from app.core.agents.conversation import ConversationAPI, ConversationManager
from app.core.harness.mcp_hub import mcp_hub
from app.core.runtime.kernel_instance import kernel
from app.store.database import db

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    ConversationAPI.delete(conv_id)
    return {"status": "ok"}


@router.patch("/conversations/{conv_id}")
async def update_conversation(conv_id: str, title: str | None = None):
    """Update conversation title."""
    ConversationAPI.update(conv_id, title=title)
    return {"status": "ok"}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, limit: int = 100):
    """Get messages for a conversation."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return db.get_recent_messages(conv_id, limit=limit)


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: dict):
    """Send a message and get a streaming response.

    Request body: {"content": "user message text"}
    """
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")

    brain = Brain()
    conversation = ConversationManager(conversation_id=conv_id)

    async def event_stream():
        try:
            async for event in brain.chat_stream(conversation, content):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, body: dict):
    """Resolve a pending approval and execute the capability if approved."""
    decision = body.get("decision", "deny")
    tool_name = body.get("tool_name", "")
    tool_args = body.get("tool_args", {})
    conv_id = body.get("conv_id", "")
    tool_call_id = body.get("tool_call_id", "")

    if decision == "approve":
        kernel.emit_event(
            type="ApprovalGranted",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": tool_name, "reason": "user_approved"},
            actor="user",
        )
        # Execute the capability via mcp_hub (handles sync/async + telemetry).
        tool = mcp_hub.get_tool(tool_name)
        if tool is not None:
            result_str = await mcp_hub.invoke_tool(tool_name, tool_args)
            kernel.emit_event(
                type="CapabilityInvoked",
                aggregate_type="capability",
                aggregate_id=f"cap_{tool_name}",
                payload={"name": tool_name, "result_summary": str(result_str)[:200]},
                actor="user",
            )
        else:
            result_str = json.dumps({"status": "error", "error": f"Unknown tool: {tool_name}"})

        # Persist tool result (sole tool message for this call_id)
        db.add_message(
            conv_id=conv_id,
            role="tool",
            content=result_str,
            tool_call_id=tool_call_id,
        )
        brain = Brain()
        conversation = ConversationManager(conversation_id=conv_id)
        assistant_message = await brain.continue_after_tool_result(conversation)
        return {"status": "success", "result": result_str, "assistant_message": assistant_message}
    else:
        kernel.emit_event(
            type="ApprovalDenied",
            aggregate_type="approval",
            aggregate_id=approval_id,
            payload={"action": tool_name, "reason": "user_denied"},
            actor="user",
        )
        result_str = json.dumps({"status": "denied", "reason": "User denied the operation"})
        db.add_message(
            conv_id=conv_id,
            role="tool",
            content=result_str,
            tool_call_id=tool_call_id,
        )
        brain = Brain()
        conversation = ConversationManager(conversation_id=conv_id)
        assistant_message = await brain.continue_after_tool_result(conversation)
        return {"status": "denied", "assistant_message": assistant_message}

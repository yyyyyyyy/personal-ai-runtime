"""Chat API — conversation and message endpoints with SSE streaming."""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.conversation import ConversationAPI, ConversationManager
from app.core.brain import Brain
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

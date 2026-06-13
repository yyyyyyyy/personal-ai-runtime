"""Chat API — conversation and message endpoints with SSE streaming."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.models import ResolveApprovalRequest, SendMessageRequest
from app.core.agents.brain import Brain
from app.core.agents.conversation import ConversationAPI, ConversationManager
from app.core.agents.intent_predictor import intent_predictor
from app.core.agents.tool_markup import strip_tool_markup
from app.core.runtime.agent_orchestrator import agent_orchestrator
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
    rows = db.get_recent_messages(conv_id, limit=limit)
    result = []
    for row in rows:
        item = dict(row)
        if item.get("role") == "assistant" and item.get("content"):
            item["content"] = strip_tool_markup(item["content"])
        result.append(item)
    return result


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: SendMessageRequest):
    """Send a message and get a streaming response."""
    conv = ConversationAPI.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    content = body.content
    if not content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")

    intent = intent_predictor.classify_message(content)
    if intent.get("intent") == "planning" and intent.get("confidence", 0) >= 0.8:

        async def plan_stream():
            try:
                result = await agent_orchestrator.run_planning_task(content)
                conversation = ConversationManager(conversation_id=conv_id)
                conversation.save_user_message(content)
                conversation.save_assistant_message(result["summary"])
                from app.core.runtime.conversation_recorder import record_conversation_turn

                record_conversation_turn(conv_id, content, result["summary"])
                yield f"data: {json.dumps({'type': 'text_delta', 'content': strip_tool_markup(result['summary'])})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return StreamingResponse(
            plan_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    brain = Brain()
    conversation = ConversationManager(conversation_id=conv_id)

    async def event_stream():
        try:
            async for event in brain.chat_stream(conversation, content):
                if event.get("type") == "text_delta" and event.get("content"):
                    event["content"] = strip_tool_markup(event["content"])
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


def _load_pending_approval(approval_id: str) -> tuple[str, dict]:
    """Load action/params from the governed approval projection (authoritative)."""
    rows = kernel.query_state("approvals", id=approval_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Approval not found")
    approval = rows[0]
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
    """Resolve a pending approval and execute the capability if approved."""
    decision = body.decision
    conv_id = body.conv_id
    tool_call_id = body.tool_call_id

    tool_name, tool_args = _load_pending_approval(approval_id)
    _reject_client_approval_mismatch(body, tool_name, tool_args)

    if decision == "approve":
        cap_result = await kernel.invoke_capability(
            name=tool_name,
            args=tool_args,
            actor="user",
            pre_approved=True,
            approval_id=approval_id,
        )
        if cap_result["status"] == "success":
            result_str = cap_result["result"]
        else:
            result_str = json.dumps({
                "status": cap_result.get("status", "error"),
                "error": cap_result.get("error", "unknown"),
            })

        assistant_message = await _resume_conversation_after_approval(
            conv_id, tool_call_id, result_str,
        )
        payload: dict = {"status": "success", "result": result_str}
        if assistant_message is not None:
            from app.core.agents.tool_markup import strip_tool_markup
            payload["assistant_message"] = strip_tool_markup(assistant_message)
        return payload
    else:
        kernel.deny_approval(
            approval_id,
            action=tool_name,
            actor="user",
            reason="user_denied",
        )
        result_str = json.dumps({"status": "denied", "reason": "User denied the operation"})
        assistant_message = await _resume_conversation_after_approval(
            conv_id, tool_call_id, result_str,
        )
        payload = {"status": "denied"}
        if assistant_message is not None:
            from app.core.agents.tool_markup import strip_tool_markup
            payload["assistant_message"] = strip_tool_markup(assistant_message)
        return payload

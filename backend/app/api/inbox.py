"""Inbox API — proactive inbox app read surface."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.product.inbox import (
    generate_inbox_digest,
    latest_digest,
    list_inbox_emails,
    mark_inbox_email_status,
    poll_inbox,
)

router = APIRouter(tags=["inbox"])


class UpdateInboxStatusRequest(BaseModel):
    status: str = Field(pattern="^(pending|read|handled)$")


@router.get("/")
async def get_inbox(
    category: str | None = Query(None, pattern="^(important|actionable|ignorable)$"),
    limit: int = Query(50, ge=1, le=200),
    status: str = Query("pending", pattern="^(pending|read|handled|all)$"),
):
    if status == "all":
        return list_inbox_emails(category=category, limit=limit, status="all")
    return list_inbox_emails(category=category, limit=limit, status=status)


@router.get("/digest")
async def get_digest():
    digest = latest_digest()
    return digest or {"message": "no digest yet"}


@router.post("/poll")
async def trigger_poll(limit: int = Query(20, ge=1, le=50)):
    return await poll_inbox(limit=limit)


@router.post("/digest")
async def trigger_digest():
    digest = generate_inbox_digest()
    return digest or {"message": "no emails to digest"}


@router.patch("/{email_id}/status")
async def update_inbox_status(email_id: str, body: UpdateInboxStatusRequest):
    try:
        result = await mark_inbox_email_status(email_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return result

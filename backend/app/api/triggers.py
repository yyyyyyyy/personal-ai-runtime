"""Triggers API — manage proactive triggers."""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateTriggerRequest
from app.core.runtime.trigger_engine import trigger_engine

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


@router.post("/")
async def create_trigger(body: CreateTriggerRequest):
    name = body.name.strip()
    trigger_type = body.trigger_type
    condition = body.condition
    action_type = body.action_type
    action_config = body.action_config

    if not name or not trigger_type or not condition:
        raise HTTPException(status_code=400, detail="name, trigger_type, and condition are required")

    return trigger_engine.create_trigger(name, trigger_type, condition, action_type, action_config)


@router.get("/")
async def list_triggers():
    return trigger_engine.list_triggers()


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str):
    existing = trigger_engine.get_trigger(trigger_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Trigger not found")
    trigger_engine.delete_trigger(trigger_id)
    return {"status": "ok"}


@router.post("/evaluate")
async def evaluate_triggers():
    suggestions = trigger_engine.evaluate_all()
    return {"suggestions": suggestions or []}

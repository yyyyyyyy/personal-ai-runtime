"""Triggers API — manage proactive triggers via ReactionRegistry.

v0.6.0: replaces imperative trigger_engine with declarative ReactionRegistry.
"""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateTriggerRequest
from app.core.runtime.reaction_registry import (
    Reaction,
    ReactionThen,
    ReactionWhen,
    get_reaction_registry,
)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


@router.post("/")
async def create_trigger(body: CreateTriggerRequest):
    name = body.name.strip()
    trigger_type = body.trigger_type
    condition = body.condition
    action_config = body.action_config or {}

    if not name or not trigger_type or not condition:
        raise HTTPException(status_code=400, detail="name, trigger_type, and condition are required")

    registry = get_reaction_registry()

    when = ReactionWhen(
        event_types=condition.get("event_type") and [condition["event_type"]] or [],
        aggregate_type=condition.get("aggregate_type", ""),
        count_gte=condition.get("count", 0),
        window_days=condition.get("window_days", 1),
    )

    template = action_config.get("template", "")
    then = ReactionThen(notification_template=template)

    registry.register(Reaction(name=name, when=when, then=then))
    return {"name": name, "status": "registered"}


@router.get("/")
async def list_triggers():
    registry = get_reaction_registry()
    return registry.list_reactions()


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str):
    registry = get_reaction_registry()
    if trigger_id not in [r.name for r in registry._reactions.values()]:
        raise HTTPException(status_code=404, detail="Trigger not found")
    del registry._reactions[trigger_id]
    return {"status": "ok"}

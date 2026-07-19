"""Triggers API — manage proactive reactions via ReactionRegistry.

The path prefix is ``/api/triggers``; responses are Reaction descriptors
(see ``list_reactions``). Prefer ``gated_by`` / ``every_cycle`` /
``state_selector`` over assuming ``threshold`` alone fires.
"""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateTriggerRequest
from app.core.runtime.reaction_registry import (
    Reaction,
    ReactionThen,
    ReactionWhen,
    get_reaction_registry,
)

router = APIRouter(tags=["triggers"])


@router.post("/")
async def create_trigger(body: CreateTriggerRequest):
    name = body.name.strip()
    trigger_type = body.trigger_type
    condition = body.condition
    action_config = body.action_config or {}

    if not name or not trigger_type or not condition:
        raise HTTPException(status_code=400, detail="name, trigger_type, and condition are required")

    registry = get_reaction_registry()

    count = int(condition.get("count", 0) or 0)
    state_selector = str(condition.get("state_selector", "") or "")
    state_filters = condition.get("state_filters") or {}
    if not isinstance(state_filters, dict):
        state_filters = {}

    if state_selector and count > 0:
        from app.core.runtime.kernel.kernel_query_state import COUNT_STATE_SELECTORS

        if state_selector not in COUNT_STATE_SELECTORS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"state_selector {state_selector!r} is not supported for count gates; "
                    f"use one of: {sorted(COUNT_STATE_SELECTORS)}"
                ),
            )

    when = ReactionWhen(
        every_cycle=True,
        event_types=condition.get("event_type") and [condition["event_type"]] or [],
        aggregate_type=condition.get("aggregate_type", ""),
        count_gte=count,
        window_days=condition.get("window_days", 1),
        state_selector=state_selector,
        state_filters=state_filters,
    )

    template = action_config.get("template", "")
    then = ReactionThen(notification_template=template)

    # Metadata-only registration unless a handler is attached later.
    registry.register(Reaction(name=name, when=when, then=then))
    return {
        "name": name,
        "status": "registered",
        "note": "without a handler this reaction will not fire in evaluate_cycle",
    }


@router.get("/")
async def list_triggers():
    """List registered reactions."""
    registry = get_reaction_registry()
    return registry.list_reactions()


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str):
    registry = get_reaction_registry()
    if trigger_id not in [r.name for r in registry._reactions.values()]:
        raise HTTPException(status_code=404, detail="Trigger not found")
    del registry._reactions[trigger_id]
    return {"status": "ok"}

"""Triggers API — manage proactive reactions via ReactionRegistry.

The path prefix is ``/api/triggers``; responses are Reaction descriptors
(see ``list_reactions``). Prefer ``gated_by`` / ``every_cycle`` /
``state_selector`` over assuming ``threshold`` alone fires.
"""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateTriggerRequest
from app.core.runtime import read_ports
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["triggers"])


@router.post("/")
async def create_trigger(body: CreateTriggerRequest):
    name = body.name.strip()
    trigger_type = body.trigger_type
    condition = body.condition
    action_config = body.action_config or {}

    if not name or not trigger_type or not condition:
        raise HTTPException(status_code=400, detail="name, trigger_type, and condition are required")

    count = int(condition.get("count", 0) or 0)
    state_selector = str(condition.get("state_selector", "") or "")
    state_filters = condition.get("state_filters") or {}
    if not isinstance(state_filters, dict):
        state_filters = {}

    if state_selector and count > 0:
        if not kernel.supports_count_state(state_selector):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"state_selector {state_selector!r} is not supported for count gates; "
                    f"use one of: {sorted(read_ports.count_state_selectors())}"
                ),
            )

    template = action_config.get("template", "")
    return read_ports.register_trigger_reaction(
        name=name,
        every_cycle=True,
        event_types=condition.get("event_type") and [condition["event_type"]] or [],
        aggregate_type=condition.get("aggregate_type", ""),
        count_gte=count,
        window_days=condition.get("window_days", 1),
        state_selector=state_selector,
        state_filters=state_filters,
        notification_template=template,
    )


@router.get("/")
async def list_triggers():
    """List registered reactions."""
    return read_ports.list_trigger_reactions()


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str):
    if not read_ports.unregister_trigger_reaction(trigger_id):
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"status": "ok"}

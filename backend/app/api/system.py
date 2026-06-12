"""System API — health checks, LLM providers, data sovereignty, and system info."""

from fastapi import APIRouter, HTTPException

from app.core.agents.llm_router import llm_router
from app.product.digital_legacy import digital_legacy

router = APIRouter(prefix="/api/system", tags=["system"])

DESTROY_CONFIRM = "DESTROY_ALL_DATA"


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    from app.config import settings

    return {
        "status": "ok",
        "service": "personal-ai-runtime",
        "version": "0.9.0",
        "auth_required": bool(settings.auth_token),
    }


@router.get("/llm-providers")
async def list_llm_providers():
    """List all configured LLM providers."""
    return {
        "providers": llm_router.list_providers(),
        "default": llm_router.get_default_model(),
    }


@router.get("/info")
async def system_info():
    """Get system information."""
    from app.core.runtime.kernel_instance import kernel
    from app.store.database import db

    counts = kernel.table_counts(("conversations", "messages", "event_log"))
    with db.get_db() as conn:
        legacy_event_count = conn.execute(
            "SELECT COUNT(*) as c FROM events"
        ).fetchone()["c"]

    goal_count = len(kernel.query_state("goals", limit=10000))
    mem_count = len(kernel.query_state("memories", limit=10000))

    return {
        "conversations": counts["conversations"],
        "messages": counts["messages"],
        "goals": goal_count,
        "event_log": counts["event_log"],
        "events": legacy_event_count,
        "memories": mem_count,
        "llm_providers": len(llm_router.list_providers()),
    }


@router.post("/export")
async def export_all_data():
    """Export complete personal data snapshot as JSON."""
    return digital_legacy.export_all()


@router.post("/import")
async def import_all_data(body: dict):
    """Import personal data snapshot. Requires confirm code when not read_only."""
    snapshot = body.get("data")
    if not snapshot:
        raise HTTPException(status_code=400, detail="Missing 'data' field")
    read_only = body.get("read_only", True)
    if not read_only and body.get("confirm") != "DESTROY_AND_IMPORT":
        raise HTTPException(status_code=400, detail="Set confirm='DESTROY_AND_IMPORT' for write import")
    return digital_legacy.import_all(snapshot, read_only=read_only)


@router.delete("/data")
async def destroy_all_data(body: dict):
    """Destroy all local data. Requires confirm code."""
    if body.get("confirm") != DESTROY_CONFIRM:
        raise HTTPException(status_code=400, detail=f"confirm must be '{DESTROY_CONFIRM}'")
    return digital_legacy.destroy_all()

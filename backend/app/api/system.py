"""System API — health checks, LLM providers, and system info."""

from fastapi import APIRouter

from app.core.agents.llm_router import llm_router

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "personal-ai-os",
        "version": "0.8.0",
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
    from app.store.database import db

    with db.get_db() as conn:
        conv_count = conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
        msg_count = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        goal_count = conn.execute("SELECT COUNT(*) as c FROM goals").fetchone()["c"]
        event_count = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        mem_count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]

    return {
        "conversations": conv_count,
        "messages": msg_count,
        "goals": goal_count,
        "events": event_count,
        "memories": mem_count,
        "llm_providers": len(llm_router.list_providers()),
    }

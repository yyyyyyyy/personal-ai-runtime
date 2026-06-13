"""Memory API — manage long-term memories and user profile."""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateMemoryRequest, UpdateMemoryRequest
from app.core.agents.memory_engine import memory_engine
from app.core.agents.memory_v2 import user_profile

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/memories")
async def list_memories(category: str | None = None, limit: int = 50):
    """List all memories, optionally filtered by category."""
    return memory_engine.list_memories(category=category, limit=limit)


@router.get("/memories/grouped")
async def list_memories_grouped(limit: int = 100):
    """List memories for the Memory Explorer UI."""
    rows = memory_engine.list_memories(limit=limit)
    return {"memories": rows}


@router.post("/memories")
async def create_memory(body: CreateMemoryRequest):
    """Create a new memory manually."""
    content = body.content
    category = body.category or "fact"

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory_id = memory_engine.store_memory(content, category, source="manual")
    return {"id": memory_id, "status": "ok"}


@router.get("/memories/search")
async def search_memories(q: str, n: int = 5):
    """Search memories semantically."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    return memory_engine.search_relevant_memories(q, n_results=n)


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a specific memory."""
    memory_engine.delete_memory(memory_id)
    return {"status": "ok"}


@router.put("/memories/{memory_id}")
async def update_memory(memory_id: str, body: UpdateMemoryRequest):
    """Update a memory's content or category."""
    content = body.content
    category = body.category

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory_engine.update_memory(memory_id, content, category=category)
    return {"status": "ok"}


# --- User Profile endpoints (Memory v2) ---

@router.get("/profile")
async def get_profile():
    """Get the structured user profile."""
    return user_profile.get_profile()


@router.post("/profile/refresh")
async def refresh_profile():
    """Recalculate time decay and refresh profile confidence scores."""
    user_profile.refresh_all()
    return {"status": "ok", "profile": user_profile.get_profile()}

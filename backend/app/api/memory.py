"""Memory API — manage long-term memories."""

from fastapi import APIRouter, HTTPException
from app.core.memory_engine import memory_engine

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/memories")
async def list_memories(category: str | None = None, limit: int = 50):
    """List all memories, optionally filtered by category."""
    return memory_engine.list_memories(category=category, limit=limit)


@router.post("/memories")
async def create_memory(body: dict):
    """Create a new memory manually."""
    content = body.get("content")
    category = body.get("category", "fact")
    source = body.get("source", "manual")

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory_id = memory_engine.store_memory(content, category, source)
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
async def update_memory(memory_id: str, body: dict):
    """Update a memory's content or category."""
    content = body.get("content")
    category = body.get("category")

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory_engine.update_memory(memory_id, content, category=category)
    return {"status": "ok"}

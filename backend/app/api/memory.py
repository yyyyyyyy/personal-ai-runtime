"""Memory API — manage long-term memories and user profile."""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateMemoryRequest, UpdateMemoryRequest
from app.core.agents.memory_engine import memory_engine
from app.core.agents.user_profile import user_profile
from app.core.runtime.kernel_instance import kernel

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _get_memory(memory_id: str) -> dict | None:
    """Check if a memory exists by querying the kernel projection."""
    rows = kernel.query_state("memories", id=memory_id)
    return rows[0] if rows else None


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
    if not _get_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    memory_engine.delete_memory(memory_id)
    return {"status": "ok"}


@router.put("/memories/{memory_id}")
async def update_memory(memory_id: str, body: UpdateMemoryRequest):
    """Update a memory's content or category."""
    if not _get_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")

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


# --- AI Portrait endpoint (Phase 1: Trust Moat) ---

@router.get("/portrait")
async def get_portrait():
    """Get the AI Portrait – aggregated user understanding across all dimensions.

    Combines user profile (preferences, values, relationships, health, finance,
    career), habits from memories, and active goals into a single structured
    response with confidence scores and source references.

    Returns:
        dict with keys: profile, habits, goals, relationships
    """
    # 1. Full structured profile
    profile = user_profile.get_profile()

    # 2. Habits — memories with category="habit"
    habits = memory_engine.list_memories(category="habit", limit=50)

    # 3. Active goals — query kernel projection
    try:
        goal_rows = kernel.query_state("goals", status="active", limit=20)
    except Exception:
        goal_rows = None

    goals_progress = []
    if goal_rows:
        goals_progress = [
            {
                "id": g.get("id", ""),
                "title": g.get("title", ""),
                "progress": g.get("progress", 0),
                "importance": g.get("importance", 0),
                "deadline": g.get("deadline"),
                "last_activity_at": g.get("last_activity_at"),
            }
            for g in goal_rows
        ]

    return {
        "profile": profile,
        "habits": [
            {
                "id": h.get("id", ""),
                "content": h.get("content", ""),
                "confidence": h.get("confidence", 0.5),
                "source": h.get("source", ""),
                "origin": h.get("origin", "claim"),
                "created_at": h.get("created_at"),
            }
            for h in habits
        ],
        "goals": goals_progress,
    }


@router.post("/profile/refresh")
async def refresh_profile():
    """Recalculate time decay and refresh profile confidence scores."""
    user_profile.refresh_all()
    return {"status": "ok", "profile": user_profile.get_profile()}


# --- Memory Graph endpoints ---

# Maximum number of memories to use as edge-query sources.
# Sampling keeps response time bounded even with large memory sets.
_MAX_EDGE_QUERY_SOURCES = 20


@router.get("/graph")
async def get_memory_graph(limit: int = 50):
    """Get memory graph with relationships based on semantic similarity.

    Returns nodes (memories) and edges (relationships between similar memories).
    Edges are built by sampling up to _MAX_EDGE_QUERY_SOURCES memories as
    vector-query sources to avoid N×1 ChromaDB round-trips.
    """
    # Get all memories
    memories = memory_engine.list_memories(limit=limit)
    if not memories:
        return {"nodes": [], "edges": []}

    # Build nodes
    nodes = [
        {
            "id": mem.get("id", ""),
            "content": mem.get("content", "")[:100],
            "category": mem.get("category", "fact"),
            "confidence": mem.get("confidence", 0.5),
        }
        for mem in memories
    ]

    # Build edges based on semantic similarity
    # Sample a subset of memories as query sources to bound ChromaDB calls
    edges: list[dict] = []
    edge_set: set[tuple[str, str]] = set()

    try:
        from app.core.runtime.kernel_instance import kernel

        # Pick memories with the most content as edge-query sources
        # (longer memories tend to produce more meaningful similarity hits)
        candidates = [m for m in memories if m.get("content")]
        candidates.sort(key=lambda m: len(m["content"]), reverse=True)
        sources = candidates[:_MAX_EDGE_QUERY_SOURCES]

        for mem in sources:
            mem_id = mem.get("id", "")
            content = mem.get("content", "")

            similar = kernel.recall_memory(content, k=5)
            for hit in similar:
                other_id = hit.get("id", "")
                if other_id == mem_id or not other_id:
                    continue

                edge_key = tuple(sorted([mem_id, other_id]))
                if edge_key in edge_set:
                    continue
                edge_set.add(edge_key)

                distance = hit.get("distance", 1.0)
                weight = max(0.1, 1.0 - distance)
                edges.append({
                    "source": mem_id,
                    "target": other_id,
                    "weight": round(weight, 2),
                })
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Memory graph: vector search failed, returning nodes without edges",
            exc_info=True,
        )

    edges.sort(key=lambda e: e["weight"], reverse=True)
    edges = edges[:100]

    return {"nodes": nodes, "edges": edges}

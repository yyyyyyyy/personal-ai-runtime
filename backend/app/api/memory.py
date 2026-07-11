"""Memory API — manage long-term memories and user profile."""

from fastapi import APIRouter, HTTPException

from app.api.models import CreateMemoryRequest, UpdateMemoryRequest
from app.core.agents.memory_engine import memory_engine
from app.core.agents.user_profile import user_profile
from app.core.runtime.kernel_instance import kernel

router = APIRouter(tags=["memory"])


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
    """Create a new memory manually. **@public** SDK surface — external agents may call this to store a fact."""
    content = body.content
    category = body.category or "fact"

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory_id = memory_engine.store_memory(content, category, source="manual")
    return {"id": memory_id, "status": "ok"}


@router.get("/memories/search")
async def search_memories(q: str, n: int = 5):
    """Search memories semantically. **@public** SDK surface — external agents may call this to recall what the user knows."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    return memory_engine.search_relevant_memories(q, n_results=n)


@router.get("/memories/{memory_id}/provenance")
async def get_memory_provenance(memory_id: str):
    """Return the full event chain for a memory — the explainability backbone.

    Surfaces every Memory* event (Derived/Updated/Decayed/Deleted) plus
    claim-status transitions, so the frontend can render:
      "conversation → MemoryExtractor → derived (conf 0.85)
       → decayed to 0.6 after 30d → ratified to 0.95"

    This is the EVENT primitive's product payoff: unlike opaque memory stores,
    every belief is fully reconstructable from its event history.
    """
    if not _get_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")

    events = kernel.read_events(
        aggregate_type="memory", aggregate_id=memory_id, order="asc"
    )
    chain = []
    for evt in events:
        chain.append({
            "seq": evt.seq,
            "type": evt.type,
            "ts": evt.ts,
            "actor": evt.actor,
            "payload": evt.payload,
            "correlation_id": evt.correlation_id,
        })
    return {"memory_id": memory_id, "events": chain}


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


# --- Claim authority endpoints (Phase 1: user confirms/corrects memories) ---

@router.post("/memories/{memory_id}/ratify")
async def ratify_memory(memory_id: str):
    """Confirm an AI-inferred memory as correct."""
    mem = _get_memory(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    if mem.get("origin") != "claim":
        raise HTTPException(
            status_code=400, detail="Only inferred (claim) memories can be ratified")

    kernel.emit_event(
        "ClaimRatified", "memory", memory_id,
        payload={"by": "user"},
        actor="user",
    )
    return {"status": "ok", "claim_status": "ratified"}


@router.post("/memories/{memory_id}/reject")
async def reject_memory(memory_id: str):
    """Reject an AI-inferred memory as incorrect."""
    mem = _get_memory(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    if mem.get("origin") != "claim":
        raise HTTPException(
            status_code=400, detail="Only inferred (claim) memories can be rejected")

    kernel.emit_event(
        "ClaimRejected", "memory", memory_id,
        payload={"by": "user"},
        actor="user",
    )
    return {"status": "ok", "claim_status": "rejected"}


@router.post("/memories/{memory_id}/contest")
async def contest_memory(memory_id: str):
    """Mark an AI-inferred memory as contested (needs correction)."""
    mem = _get_memory(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    if mem.get("origin") != "claim":
        raise HTTPException(
            status_code=400, detail="Only inferred (claim) memories can be contested")

    kernel.emit_event(
        "ClaimContested", "memory", memory_id,
        payload={"by": "user"},
        actor="user",
    )
    return {"status": "ok", "claim_status": "contested"}


# --- AI Portrait endpoint (Phase 1: Trust Moat) ---

@router.get("/portrait")
async def get_portrait():
    """Get the AI Portrait – aggregated user understanding across all dimensions.

    Combines user profile (preferences, values, relationships, health, finance,
    career), habits from memories, and active goals into a single structured
    response with confidence scores and source references.

    Returns:
        dict with keys: profile, habits, goals
    """
    # 1. Full structured profile
    profile = user_profile.get_profile()

    # 2. Habits — memories with category="habit"
    habits = memory_engine.list_memories(category="habit", limit=50)

    # 3. Active goals (v1.0 Phase 4: goals table retired)
    try:
        goal_rows = kernel.query_state(
            "work_items", work_type="goal", status="active", limit=20,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Portrait: failed to query goals projection, returning empty goals list",
            exc_info=True,
        )
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


# --- Memory Graph endpoints ---

# Maximum number of memories to use as edge-query sources.
# Sampling keeps response time bounded even with large memory sets.
_MAX_EDGE_QUERY_SOURCES = 20


@router.get("/graph")
async def get_memory_graph(limit: int = 50):
    """Get memory graph with relationships based on semantic similarity.

    Returns nodes (memories) and edges (relationships between similar memories).
    Edges are built by sampling up to _MAX_EDGE_QUERY_SOURCES memories and
    running a **single** batched Chroma query (not N round-trips).
    """
    import asyncio

    memories = memory_engine.list_memories(limit=limit)
    if not memories:
        return {"nodes": [], "edges": []}

    nodes = [
        {
            "id": mem.get("id", ""),
            "content": mem.get("content", "")[:100],
            "category": mem.get("category", "fact"),
            "confidence": mem.get("confidence", 0.5),
        }
        for mem in memories
    ]

    # Longer memories tend to produce more meaningful similarity hits.
    candidates = [m for m in memories if m.get("content")]
    candidates.sort(key=lambda m: len(m["content"]), reverse=True)
    sources = candidates[:_MAX_EDGE_QUERY_SOURCES]

    try:
        edges = await asyncio.to_thread(_build_memory_graph_edges, sources)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Memory graph: vector search failed, returning nodes without edges",
            exc_info=True,
        )
        edges = []

    return {"nodes": nodes, "edges": edges}


def _build_memory_graph_edges(sources: list[dict]) -> list[dict]:
    """Build similarity edges via one batched vector query (sync, for to_thread)."""
    from app.store.vector import vector_store

    if not sources:
        return []

    query_texts = [m.get("content", "") for m in sources]
    batches = vector_store.search_memories_batch(query_texts, n_results=5)

    edges: list[dict] = []
    edge_set: set[tuple[str, str]] = set()

    for mem, similar in zip(sources, batches, strict=False):
        mem_id = mem.get("id", "")
        for hit in similar:
            other_id = hit.get("id", "")
            if other_id == mem_id or not other_id:
                continue
            edge_key = tuple(sorted([mem_id, other_id]))
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)
            distance = hit.get("distance", 1.0) or 1.0
            weight = max(0.1, 1.0 - float(distance))
            edges.append({
                "source": mem_id,
                "target": other_id,
                "weight": round(weight, 2),
            })

    edges.sort(key=lambda e: e["weight"], reverse=True)
    return edges[:100]

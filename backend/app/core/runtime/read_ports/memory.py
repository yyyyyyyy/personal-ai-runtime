"""Memory projection and retrieval read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def retrieve_memory_context(query: str, *, max_memories: int = 3) -> str:
    from app.core.agents.memory_engine import memory_engine

    return memory_engine.retrieve_context_string(query, max_memories=max_memories)


def retrieve_memory_with_sources(query: str, *, max_memories: int = 3) -> tuple[str, list[dict]]:
    """Retrieve memory context and return (context_str, sources)."""
    from app.core.agents.memory_engine import memory_engine

    hits = memory_engine.search_relevant_memories(query, n_results=max_memories)
    enriched = memory_engine._enrich_recall_hits(hits)
    context_str = memory_engine.format_memory_context(enriched)
    sources = [
        {"id": mem["id"], "type": "memory", "title": mem.get("content", "")[:80]}
        for mem in enriched
        if mem.get("id")
    ]
    return context_str, sources


def query_memory(memory_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("memories", id=memory_id, limit=1)
    return rows[0] if rows else None


def query_memories(
    *,
    category: str | None = None,
    limit: int = 5000,
    order: str | None = None,
    confidence_gt: float | None = None,
    confidence_lt: float | None = None,
    decay_eligible: bool | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"limit": limit}
    if category:
        filters["category"] = category
    if order:
        filters["order"] = order
    if confidence_gt is not None:
        filters["confidence_gt"] = confidence_gt
    if confidence_lt is not None:
        filters["confidence_lt"] = confidence_lt
    if decay_eligible is not None:
        filters["decay_eligible"] = decay_eligible
    return kernel().query_state("memories", **filters)


def build_memory_graph_edges(sources: list[dict]) -> list[dict]:
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


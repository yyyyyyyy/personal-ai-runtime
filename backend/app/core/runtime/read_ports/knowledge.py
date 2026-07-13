"""Knowledge recall and unified retrieval read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel, logger


def recall_unified(
    query: str,
    *,
    k_memories: int = 3,
    k_knowledge: int = 3,
) -> list[dict]:
    """Unified semantic recall across memories AND knowledge documents.

    Combines kernel().recall_memory + kernel().recall_knowledge into a single
    ranked list. Each item carries source_type ("memory" | "document") and
    provenance (source field for memories, source_file metadata for documents).

    Implemented here (read_ports) rather than in the Kernel because it is a
    pure composition of the two existing recall ABI methods — keeping it out
    of the Kernel avoids growing the God Object (concept-zero-sum contract).
    """
    results: list[dict] = []

    try:
        for hit in kernel().recall_memory(query, k=k_memories):
            mem_id = hit.get("id") or ""
            provenance = ""
            if mem_id:
                rows = kernel().query_state("memories", id=mem_id)
                if rows:
                    provenance = rows[0].get("source", "") or ""
            results.append({
                "id": mem_id,
                "content": hit.get("content", ""),
                "source_type": "memory",
                "provenance": provenance,
                "distance": hit.get("distance"),
                "metadata": hit.get("metadata") or {},
            })
    except Exception:
        logger.warning("recall_unified: memory recall failed", exc_info=True)

    try:
        for hit in kernel().recall_knowledge(query, k=k_knowledge):
            meta = hit.get("metadata") or {}
            results.append({
                "id": hit.get("id") or "",
                "content": hit.get("content", ""),
                "source_type": "document",
                "provenance": meta.get("source_file", ""),
                "distance": hit.get("distance"),
                "metadata": meta,
            })
    except Exception:
        logger.warning("recall_unified: knowledge recall failed", exc_info=True)

    def _rank_key(item: dict) -> float:
        d = item.get("distance")
        return d if d is not None else float("inf")

    results.sort(key=_rank_key)
    return results


def retrieve_unified_with_sources(
    query: str,
    *,
    max_memories: int = 3,
    max_knowledge: int = 3,
) -> tuple[str, list[dict]]:
    """Unified retrieval across memories AND knowledge documents.

    Returns (context_str, sources) where sources may contain both:
      - {"type": "memory", "id": ..., "title": ...}
      - {"type": "document", "id": ..., "title": <filename>}

    The context_str renders a "## 相关记忆" section followed by a
    "## 相关文档" section so the LLM sees both, and the frontend can
    surface both as citations via the sources event.
    """
    if not query or len(query.strip()) < 2:
        return "", []

    unified = recall_unified(query, k_memories=max_memories, k_knowledge=max_knowledge)

    mem_items = [u for u in unified if u.get("source_type") == "memory"]
    doc_items = [u for u in unified if u.get("source_type") == "document"]

    parts: list[str] = []
    sources: list[dict] = []

    if mem_items:
        lines = ["## 相关记忆"]
        for i, mem in enumerate(mem_items, 1):
            lines.append(f"{i}. {mem.get('content', '')}")
        parts.append("\n".join(lines))
        sources.extend(
            {"id": m.get("id", ""), "type": "memory", "title": (m.get("content", "") or "")[:80]}
            for m in mem_items
            if m.get("id")
        )

    if doc_items:
        lines = ["## 相关文档"]
        for i, doc in enumerate(doc_items, 1):
            fname = doc.get("provenance") or "document"
            snippet = (doc.get("content", "") or "")[:300].strip().replace("\n", " ")
            lines.append(f"{i}. [{fname}] {snippet}")
        parts.append("\n".join(lines))
        sources.extend(
            {
                "id": d.get("id", ""),
                "type": "document",
                "title": d.get("provenance") or "document",
            }
            for d in doc_items
            if d.get("id")
        )

    return ("\n\n".join(parts), sources) if parts else ("", [])


def search_knowledge(query: str, *, n_results: int = 3) -> list[dict[str, Any]]:
    return kernel().recall_knowledge(query, k=n_results)


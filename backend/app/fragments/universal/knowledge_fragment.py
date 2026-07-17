"""Knowledge retrieval helper for scenario.knowledge fragment.

Queries ChromaDB via read_ports (fragment read boundary). Returns prompt
text and citation sources from a single search.
"""

from __future__ import annotations

from app.core.agents.token_counter import count_text_tokens
from app.core.runtime import read_ports

TOP_K = 3
_SNIPPET_CHARS = 500
_MIN_QUERY_LEN = 4
# Cosine distance ≈ 1 - similarity; drop weak matches when distance is present.
_MAX_DISTANCE = 0.85
_SNIPPET_FALLBACKS = (500, 240, 120)


def _hit_distance(hit: dict) -> float | None:
    raw = hit.get("distance")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _format_entry(index: int, fname: str, snippet: str) -> str:
    return f"{index}. [{fname}] {snippet}"


def retrieve_knowledge_with_sources(
    user_message: str,
    *,
    max_tokens: int = 1500,
    n_results: int = TOP_K,
    max_distance: float = _MAX_DISTANCE,
) -> tuple[str, list[dict]]:
    """Single-pass knowledge recall → (content, sources).

    Packs entries one-by-one under ``max_tokens``. Sources only include
    documents that actually appear in the returned content.
    """
    query = (user_message or "").strip()
    if len(query) < _MIN_QUERY_LEN:
        return "", []

    try:
        results = read_ports.search_knowledge(query, n_results=n_results)
    except Exception:
        return "", []

    if not results:
        return "", []

    header = "## 相关文档"
    header_tokens = count_text_tokens(header)
    if header_tokens >= max_tokens:
        return "", []

    lines = [header]
    sources: list[dict] = []
    used = header_tokens
    index = 1

    for hit in results:
        distance = _hit_distance(hit)
        if distance is not None and distance > max_distance:
            continue

        content = str(hit.get("content") or "").strip()
        if not content:
            continue
        meta = hit.get("metadata") or {}
        fname = str(meta.get("source_file") or "document")

        chosen_line = ""
        for snip_len in _SNIPPET_FALLBACKS:
            snippet = content[:snip_len].replace("\n", " ").strip()
            if not snippet:
                break
            candidate = _format_entry(index, fname, snippet)
            # +1 approximates the joining newline.
            cost = count_text_tokens(candidate) + 1
            if used + cost <= max_tokens:
                chosen_line = candidate
                break

        if not chosen_line:
            # No room even for a short snippet — stop packing further hits.
            break

        lines.append(chosen_line)
        used += count_text_tokens(chosen_line) + 1
        doc_id = str(hit.get("id") or "").strip()
        if doc_id:
            sources.append({"id": doc_id, "type": "document", "title": fname})
        index += 1

    if len(lines) == 1:
        return "", []
    return "\n".join(lines), sources


def build_knowledge_context(user_message: str) -> str | None:
    """Backward-compatible helper — content only (sync)."""
    content, _sources = retrieve_knowledge_with_sources(user_message)
    return content or None

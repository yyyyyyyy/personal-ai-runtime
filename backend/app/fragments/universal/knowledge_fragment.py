"""Knowledge Context Fragment - injects relevant knowledge into system prompt.

This fragment queries ChromaDB via read_ports (respecting fragment read boundary).
Loaded in Scenario Tier when the user's intent contains 'knowledge' tags.
"""

from app.core.runtime import read_ports

MAX_KNOWLEDGE_CHARS = 1500
TOP_K = 3


async def build_knowledge_context(user_message: str) -> str | None:
    """Retrieve relevant knowledge chunks and format them for context injection.

    Returns None if no relevant knowledge is found.
    """
    if not user_message or len(user_message.strip()) < 3:
        return None

    try:
        results = read_ports.search_knowledge(user_message, n_results=TOP_K)
    except Exception:
        return None

    if not results:
        return None

    parts = []
    total_chars = 0

    for r in results:
        content = r.get("content", "")
        source = (r.get("metadata") or {}).get("source_file", "unknown")
        snippet = content[:500].strip()
        entry = "[Source: {source}] {snippet}".format(source=source, snippet=snippet)
        if total_chars + len(entry) > MAX_KNOWLEDGE_CHARS:
            break
        parts.append(entry)
        total_chars += len(entry)

    if not parts:
        return None

    header = "Relevant knowledge from user's document library:"
    return header + "\n" + "\n\n".join(parts)

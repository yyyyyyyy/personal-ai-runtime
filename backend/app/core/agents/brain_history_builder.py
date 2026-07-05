"""Brain History Builder — constructs the LLM messages array.

Extracted from Brain._build_messages (v0.10.0) so the history assembly
logic is independently testable. Handles:

- Injection of system_prompt as the first message
- Long-context truncation (capped by ``settings.max_recent_messages``)
- Tool-call sequence validation (strips orphaned tool_calls to avoid
  DeepSeek API 400 errors)
- Tool-result compaction via ``compact_for_llm``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.core.agents.tool_postprocess import compact_for_llm

if TYPE_CHECKING:
    from app.core.agents.conversation import ConversationManager

logger = logging.getLogger(__name__)


def build_messages(
    conversation: "ConversationManager",
    user_message: str,
    *,
    system_prompt: str,
) -> list[dict]:
    """Build the messages array for the LLM.

    system_prompt must be produced by PromptCompiler (artifact + fragments).
    """
    if not system_prompt or not system_prompt.strip():
        raise RuntimeError(
            "system_prompt must be compiled before calling Brain",
        )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history. Enforce that every assistant tool_calls
    # is immediately followed by ALL its tool result messages, otherwise
    # strip to avoid DeepSeek API 400 errors.
    history = conversation.get_history()

    # Long-context mitigation: cap the number of history turns we send.
    # Older turns are dropped (the system prompt + memory fragments already
    # carry the durable facts). We keep the most recent window so tool-call
    # sequences stay intact.
    max_history: int = getattr(settings, "max_recent_messages", 50)
    if len(history) > max_history:
        dropped = len(history) - max_history
        history = history[-max_history:]
        logger.debug(
            "Truncated %d older history message(s) before LLM call", dropped,
        )

    # First, tag each message with its parsed tool data
    tagged: list[dict] = []
    for msg in history:
        tc = msg.get("tool_calls")
        tagged.append({
            "role": msg["role"],
            "content": msg["content"] or "",
            "tool_calls": tc,  # already parsed list from conversation.py
            "tool_call_id": msg.get("tool_call_id"),
        })

    # Scan for valid sequences: assistant_with_calls → N×tool_results
    # Mark which indices to keep and which tool_calls to strip
    keep_tool_calls: dict[int, bool] = {}
    keep_tool_result: dict[int, bool] = {}

    i = 0
    while i < len(tagged):
        m = tagged[i]
        if m["role"] == "assistant" and m["tool_calls"]:
            required_ids = {t["id"] for t in m["tool_calls"] if t.get("id")}
            j = i + 1
            satisfied_ids: set[str] = set()
            while j < len(tagged) and tagged[j]["role"] == "tool":
                tid = tagged[j].get("tool_call_id")
                if tid is not None and tid in required_ids:
                    satisfied_ids.add(tid)
                j += 1
            if satisfied_ids == required_ids and required_ids:
                keep_tool_calls[i] = True
                for k in range(i + 1, j):
                    tid = tagged[k].get("tool_call_id")
                    if tid in required_ids:
                        keep_tool_result[k] = True
        i += 1

    # Pre-build tool_name lookup from tool_call_id to tool name (O(n) once)
    tool_name_by_id: dict[str, str] = {}
    for tc_msg in tagged:
        if tc_msg.get("role") == "assistant" and tc_msg.get("tool_calls"):
            for tcall in tc_msg["tool_calls"]:
                if tcall.get("id"):
                    tool_name_by_id[tcall["id"]] = (
                        tcall.get("function", {}).get("name", "")
                    )

    # Second pass: build messages respecting the validated structure
    for idx, msg in enumerate(tagged):
        if msg["role"] == "tool":
            if keep_tool_result.get(idx):
                tool_content: str = msg["content"] or ""
                tool_name_guess = tool_name_by_id.get(msg.get("tool_call_id") or "", "")
                if tool_name_guess:
                    tool_content = compact_for_llm(tool_name_guess, tool_content)
                messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": tool_content,
                })
            continue

        item: dict = {"role": msg["role"], "content": msg["content"]}
        if msg["role"] == "assistant" and msg["tool_calls"] and keep_tool_calls.get(idx):
            item["tool_calls"] = msg["tool_calls"]
        messages.append(item)

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    return messages

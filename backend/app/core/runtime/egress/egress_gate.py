"""LLM Egress gate — audit and redact before outbound API calls."""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.core.runtime import kernel_instance

_IDENTITY_MARKERS = (
    re.compile(r"identity_narrative_opt_in"),
    re.compile(r"claim_status"),
    re.compile(r"career-entrepreneurship"),
    re.compile(r"系统投影"),
)


def classify_llm_payload(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify outbound LLM message content for audit."""
    combined = "\n".join(str(m.get("content") or "") for m in messages)
    categories: list[str] = []
    if any(p.search(combined) for p in _IDENTITY_MARKERS):
        categories.append("identity_surface")
    if "memory_id:" in combined or "memories" in combined.lower():
        categories.append("memory_context")
    if "event_seq" in combined or "trajectory" in combined.lower():
        categories.append("trajectory_context")
    if not categories:
        categories.append("general")
    return {
        "categories": categories,
        "message_count": len(messages),
        "char_count": len(combined),
    }


def _redact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Redact high-sensitivity identity markers in outbound copy (audit original retained)."""
    redacted: list[dict[str, Any]] = []
    for msg in messages:
        content = str(msg.get("content") or "")
        for pat in _IDENTITY_MARKERS:
            content = pat.sub("[redacted]", content)
        redacted.append({**msg, "content": content})
    return redacted


def prepare_llm_egress(
    messages: list[dict[str, Any]],
    *,
    purpose: str,
    actor: str = "kernel",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit egress, emit EgressApproved, return (messages_for_api, audit_meta)."""
    classification = classify_llm_payload(messages)
    needs_redact = "identity_surface" in classification["categories"]
    outbound = _redact_messages(messages) if needs_redact else messages

    audit = {
        "purpose": purpose,
        "classification": classification,
        "redacted": needs_redact,
    }

    k = kernel_instance.kernel
    k.emit_event(
        "EgressApproved",
        "egress",
        f"egress_{uuid.uuid4().hex[:12]}",
        payload=audit,
        actor=actor,
    )

    return outbound, audit


def prepare_llm_egress_sync(
    messages: list[dict[str, Any]],
    *,
    purpose: str,
    actor: str = "kernel",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return prepare_llm_egress(messages, purpose=purpose, actor=actor)

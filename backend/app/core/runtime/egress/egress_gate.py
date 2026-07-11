"""LLM Egress Audit — outbound call logging (not a PII redaction boundary).

Records what leaves the machine for audit. Classification is heuristic only;
messages are passed through unchanged — no redaction or sanitization.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.core.runtime import kernel_instance

# Structural field-name patterns for audit classification (not doc-example literals).
_AUDIT_CLASSIFIERS = (
    re.compile(r"identity_narrative_opt_in"),
    re.compile(r"claim_status"),
)


def classify_llm_payload(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify outbound LLM message content for audit logging."""
    combined = "\n".join(str(m.get("content") or "") for m in messages)
    categories: list[str] = []
    if any(p.search(combined) for p in _AUDIT_CLASSIFIERS):
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


def audit_llm_egress(
    messages: list[dict[str, Any]],
    *,
    purpose: str,
    actor: str = "kernel",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Audit outbound LLM call, emit EgressAudited, return (messages, audit_meta).

    Messages are returned unchanged — this is audit-only, not a redaction boundary.
    """
    classification = classify_llm_payload(messages)
    identity_surface = "identity_surface" in classification["categories"]

    audit = {
        "purpose": purpose,
        "classification": classification,
        "identity_surface_detected": identity_surface,
    }

    k = kernel_instance.kernel
    k.emit_event(
        "EgressAudited",
        "egress",
        f"egress_{uuid.uuid4().hex[:12]}",
        payload=audit,
        actor=actor,
    )

    return messages, audit


def audit_llm_egress_sync(
    messages: list[dict[str, Any]],
    *,
    purpose: str,
    actor: str = "kernel",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return audit_llm_egress(messages, purpose=purpose, actor=actor)

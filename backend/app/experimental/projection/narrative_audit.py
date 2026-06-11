"""Build auditable narrative metadata for Identity RFC §3.3 trace."""

from __future__ import annotations

import json
import re
from typing import Any

from app.experimental.projection.identity_lint import _trajectory_mentioned

_OUTCOME_LEGACY_TYPES = frozenset({"outcome", "observation", "outcome_observation"})
_DESTINY_IN_CONTENT = re.compile(r"你是[\u4e00-\u9fff]{1,24}")


def _parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _event_seq(row: dict[str, Any]) -> int | None:
    for key in ("seq", "event_seq"):
        if row.get(key) is not None:
            return int(row[key])
    return None


def _is_outcome_event(row: dict[str, Any]) -> bool:
    payload = _parse_payload(row)
    if payload.get("evidence_type") == "outcome":
        return True
    legacy_type = (row.get("type") or "").lower()
    return legacy_type in _OUTCOME_LEGACY_TYPES


def _belief_cited_in_content(content: str, excerpt: str) -> bool:
    excerpt = (excerpt or "").strip()
    if not excerpt:
        return False
    if excerpt in content:
        return True
    snippet = excerpt[:24]
    return len(snippet) >= 6 and snippet in content


def build_narrative_audit(
    content: str,
    trajectories: list[dict[str, Any]] | None = None,
    *,
    memories: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    trajectory_link_seqs: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """Populate narrative_audit for review key_insights (heuristic / template-safe)."""
    trajectories = trajectories or []
    memories = memories or []
    events = events or []
    trajectory_link_seqs = trajectory_link_seqs or {}

    cited_trajectory_ids = [
        t["id"]
        for t in trajectories
        if t.get("id") and _trajectory_mentioned(content, t)
    ]

    cited_beliefs: list[dict[str, Any]] = []
    for mem in memories:
        if mem.get("origin") != "claim":
            continue
        excerpt = (mem.get("content") or "").strip()
        if not excerpt:
            continue
        if not _belief_cited_in_content(content, excerpt):
            continue
        cited_beliefs.append({
            "memory_id": mem.get("id"),
            "claim_status": mem.get("claim_status") or "proposed",
            "excerpt": excerpt[:240],
            "in_content": True,
        })

    outcome_event_seqs: list[int] = []
    for row in events:
        seq = _event_seq(row)
        if seq is not None and _is_outcome_event(row):
            outcome_event_seqs.append(seq)

    identity_claims: list[dict[str, Any]] = []
    for tid in cited_trajectory_ids:
        entry = next((t for t in trajectories if t.get("id") == tid), {})
        evidence_seqs = trajectory_link_seqs.get(tid, [])
        claim_text = f"{tid}: {entry.get('description', tid)}"
        if _DESTINY_IN_CONTENT.search(content):
            for match in _DESTINY_IN_CONTENT.finditer(content):
                identity_claims.append({
                    "text": match.group(0),
                    "evidence_event_seqs": evidence_seqs,
                    "evidence_types": ["trajectory"] if evidence_seqs else ["narrative"],
                })
        else:
            identity_claims.append({
                "text": claim_text,
                "evidence_event_seqs": evidence_seqs,
                "evidence_types": ["trajectory"],
            })

    return {
        "cited_trajectory_ids": cited_trajectory_ids,
        "cited_beliefs": cited_beliefs,
        "identity_claims": identity_claims,
        "outcome_event_seqs": sorted(set(outcome_event_seqs)),
    }

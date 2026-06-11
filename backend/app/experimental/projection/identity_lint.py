"""Identity RFC N1–N5 + I-F1–F3 — heuristic lint for identity narrative content."""

from __future__ import annotations

import re
from typing import Any

# N2 / I-F3 — recurrence framed as destiny
N2_FORBIDDEN_PATTERNS = [
    re.compile(r"你就是这样的人"),
    re.compile(r"你一直是[\u4e00-\u9fff]{1,8}型"),
    re.compile(r"你本来就是"),
    re.compile(r"天生适合"),
]

I_F3_PROPOSED_DESTINY = re.compile(r"你是[\u4e00-\u9fff]{1,24}")

# N3 / I-F1 — outcome epilogue / backfill phrasing
N3_FORBIDDEN_PATTERNS = [
    re.compile(r"当年(的)?选择是正确的"),
    re.compile(r"证明了你(当时)?是对的"),
    re.compile(r"事实证明你"),
    re.compile(r"说明你(一直|本来就)"),
]


def _trajectory_mentioned(content: str, trajectory: dict[str, Any]) -> bool:
    tid = trajectory.get("id") or ""
    if tid and tid in content:
        return True
    desc = trajectory.get("description") or ""
    if desc and len(desc) >= 8 and desc[:24] in content:
        return True
    domain = trajectory.get("domain") or ""
    if domain and f"domain:{domain}" in content:
        return True
    return False


def lint_i_f1_outcome_monoculture(narrative_meta: dict[str, Any]) -> list[str]:
    """I-F1: identity-class claim supported only by a single Outcome event_seq."""
    violations: list[str] = []
    outcome_seqs = {
        int(x)
        for x in narrative_meta.get("outcome_event_seqs", [])
    }
    for claim in narrative_meta.get("identity_claims", []):
        evidence = [int(s) for s in claim.get("evidence_event_seqs", [])]
        if len(evidence) != 1:
            continue
        seq = evidence[0]
        if seq in outcome_seqs or claim.get("evidence_types") == ["outcome"]:
            violations.append(
                f"FAIL:I-F1 identity claim {claim.get('text', '')!r} "
                f"supported only by outcome event_seq={seq}"
            )
    return violations


def lint_i_f2_competing_visibility(
    content: str,
    trajectories: list[dict[str, Any]],
    *,
    released_trajectory_ids: set[str] | None = None,
) -> list[str]:
    """I-F2: competing trajectory mentioned on one side only (N4 hard fail)."""
    violations: list[str] = []
    released = released_trajectory_ids or set()
    registry = {t.get("id"): t for t in trajectories if t.get("id")}

    seen_pairs: set[tuple[str, str]] = set()
    for tid, entry in registry.items():
        for other in entry.get("competing_with") or []:
            if other not in registry:
                continue
            pair = tuple(sorted((tid, other)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            if tid in released or other in released:
                continue

            a_on = _trajectory_mentioned(content, entry)
            b_on = _trajectory_mentioned(content, registry[other])
            if a_on and not b_on:
                violations.append(
                    f"FAIL:I-F2 trajectory {tid!r} appears but competing {other!r} absent"
                )
            elif b_on and not a_on:
                violations.append(
                    f"FAIL:I-F2 trajectory {other!r} appears but competing {tid!r} absent"
                )
    return violations


def lint_i_f3_proposed_belief_destiny(
    content: str,
    narrative_meta: dict[str, Any],
) -> list[str]:
    """I-F3: proposed Belief framed as definitive identity ('你是…')."""
    violations: list[str] = []
    for belief in narrative_meta.get("cited_beliefs", []):
        if belief.get("claim_status") != "proposed":
            continue
        excerpt = belief.get("excerpt") or content
        if I_F3_PROPOSED_DESTINY.search(excerpt):
            violations.append(
                f"FAIL:I-F3 proposed belief {belief.get('memory_id', '?')!r} "
                f"uses destiny framing: {excerpt[:40]!r}"
            )
    return violations


def lint_identity_hard_failures(
    content: str,
    *,
    trajectories: list[dict[str, Any]] | None = None,
    narrative_meta: dict[str, Any] | None = None,
    released_trajectory_ids: set[str] | None = None,
) -> list[str]:
    """Return I-F1..I-F3 hard failures (empty = pass)."""
    trajectories = trajectories or []
    narrative_meta = narrative_meta or {}
    violations: list[str] = []
    violations.extend(lint_i_f1_outcome_monoculture(narrative_meta))
    violations.extend(
        lint_i_f2_competing_visibility(
            content, trajectories, released_trajectory_ids=released_trajectory_ids
        )
    )
    violations.extend(lint_i_f3_proposed_belief_destiny(content, narrative_meta))
    return violations


def lint_review_content(
    content: str,
    *,
    trajectories: list[dict[str, Any]] | None = None,
    narrative_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Return violation messages (empty = pass). Warnings and fails prefixed."""
    violations: list[str] = []
    trajectories = trajectories or []
    narrative_meta = narrative_meta or {}

    for pat in N2_FORBIDDEN_PATTERNS:
        if pat.search(content):
            violations.append(f"FAIL:N2 destiny framing matched {pat.pattern!r}")

    for pat in N3_FORBIDDEN_PATTERNS:
        if pat.search(content):
            violations.append(f"FAIL:N3 outcome epilogue matched {pat.pattern!r}")

    violations.extend(
        lint_identity_hard_failures(
            content, trajectories=trajectories, narrative_meta=narrative_meta
        )
    )

    # N4 — competing trajectories should be visible when registry has pairs
    competing_pairs = [
        (t.get("id"), c)
        for t in trajectories
        for c in (t.get("competing_with") or [])
    ]
    if competing_pairs and "竞争轨迹" not in content and "轨迹视角" not in content:
        violations.append("WARN:N4 competing trajectories exist but section missing")

    # N1 — monoculture: single trajectory id dominates narrative body (heuristic)
    if trajectories:
        ids = [t.get("id", "") for t in trajectories if t.get("id")]
        if len(ids) >= 2:
            mentioned = [tid for tid in ids if tid in content]
            if len(mentioned) == 1 and "竞争" not in content:
                violations.append(
                    f"WARN:N1 only one trajectory mentioned ({mentioned[0]}) among {len(ids)}"
                )

    violations.extend(
        lint_identity_warnings(content, trajectories=trajectories, narrative_meta=narrative_meta)
    )
    return violations


def lint_identity_warnings(
    content: str,
    *,
    trajectories: list[dict[str, Any]] | None = None,
    narrative_meta: dict[str, Any] | None = None,
) -> list[str]:
    """I-W1–W3 heuristic warnings."""
    violations: list[str] = []
    trajectories = trajectories or []
    narrative_meta = narrative_meta or {}

    cited_ids = narrative_meta.get("cited_trajectory_ids") or []
    if len(cited_ids) == 1 and len(trajectories) >= 2:
        violations.append(f"WARN:I-W1 narrative cites single trajectory {cited_ids[0]!r}")

    if cited_ids and trajectories:
        domains = [
            t.get("domain", "general")
            for t in trajectories
            if t.get("id") in cited_ids
        ]
        if domains:
            dominant = max(set(domains), key=domains.count)
            ratio = domains.count(dominant) / len(domains)
            if ratio >= 0.95 and len(set(domains)) > 1:
                violations.append(f"WARN:I-W2 narrative cites 95%+ from domain {dominant!r}")

    if narrative_meta.get("projection") is False:
        violations.append("WARN:I-W3 narrative_audit missing projection=true")

    return violations


def extract_narrative_audit(
    content: str,
    trajectories: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Backward-compatible wrapper — prefer build_narrative_audit."""
    from app.experimental.projection.narrative_audit import build_narrative_audit

    return build_narrative_audit(
        content,
        trajectories,
        memories=kwargs.get("memories"),
        events=kwargs.get("events"),
        trajectory_link_seqs=kwargs.get("trajectory_link_seqs"),
    )

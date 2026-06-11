"""Claim Authority — Meaning Boundary G1 epistemic state transitions.

Manages who may influence Agency: only ratified system claims (origin=claim)
can drive proactive actions. All transitions go through Kernel events.
"""

from app.core.runtime import kernel_instance

CLAIM_STATUSES = frozenset({
    "proposed", "contested", "ratified", "rejected", "released",
})


def can_present(row: dict) -> bool:
    """Whether a memory row may be shown to the user (presentation layer)."""
    if row.get("origin") == "self_report":
        return True
    if row.get("origin") != "claim":
        return True
    status = row.get("claim_status") or "proposed"
    return status not in ("rejected", "released")


def can_drive_agency(row: dict) -> bool:
    """Whether a memory row may drive proactive Agency (notifications, etc.)."""
    if row.get("origin") != "claim":
        return False
    return row.get("claim_status") == "ratified" and float(row.get("confidence") or 0) > 0


def _kernel():
    return kernel_instance.kernel


def _get_claim_row(memory_id: str) -> dict | None:
    rows = _kernel().query_state("memories", id=memory_id)
    if not rows:
        return None
    row = rows[0]
    if row.get("origin") != "claim":
        raise ValueError(f"Memory {memory_id} is not a system claim (origin={row.get('origin')!r})")
    return row


def ratify(memory_id: str, actor: str = "user") -> None:
    """User ratifies a system claim — grants Agency authority."""
    _get_claim_row(memory_id)
    _kernel().emit_event(
        "ClaimRatified", "memory", memory_id, actor=actor,
    )


def reject(memory_id: str, actor: str = "user", reason: str = "") -> None:
    """User rejects a system claim — dormant, no Agency authority."""
    _get_claim_row(memory_id)
    _kernel().emit_event(
        "ClaimRejected", "memory", memory_id,
        payload={"reason": reason} if reason else {},
        actor=actor,
    )


def contest(memory_id: str, actor: str = "user", reason: str = "") -> None:
    """User contests a system claim — visible tension, no Agency authority."""
    _get_claim_row(memory_id)
    _kernel().emit_event(
        "ClaimContested", "memory", memory_id,
        payload={"reason": reason} if reason else {},
        actor=actor,
    )


def release(memory_id: str, actor: str = "user", reason: str = "") -> None:
    """User releases influence of a ratified claim."""
    _get_claim_row(memory_id)
    _kernel().emit_event(
        "ClaimReleased", "memory", memory_id,
        payload={"reason": reason} if reason else {},
        actor=actor,
    )


def reopen(memory_id: str, actor: str = "user") -> None:
    """Reopen a rejected claim into contested state (v1 manual restart)."""
    _get_claim_row(memory_id)
    _kernel().emit_event(
        "ClaimReopened", "memory", memory_id, actor=actor,
    )


def revise(
    memory_id: str,
    content: str | None = None,
    confidence: float | None = None,
    actor: str = "user",
) -> None:
    """Revise claim content — returns to proposed, requires re-ratification."""
    _get_claim_row(memory_id)
    payload: dict = {}
    if content is not None:
        payload["content"] = content
    if confidence is not None:
        payload["confidence"] = confidence
    _kernel().emit_event(
        "ClaimRevised", "memory", memory_id, payload=payload, actor=actor,
    )


def list_actionable_claims(limit: int = 5) -> list[dict]:
    """Ratified claims eligible to drive Agency."""
    rows = _kernel().query_state("memories", origin="claim", limit=500)
    return [r for r in rows if can_drive_agency(r)][:limit]

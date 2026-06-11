"""Trajectory API — continuity interpretations (read + link)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.runtime import kernel_instance
from app.core.runtime.trajectory import identity_authority, link_authority
from app.core.runtime.trajectory.delta import compute_trajectory_delta
from app.core.runtime.trajectory.engine import link_event, register_trajectory

router = APIRouter(prefix="/api/trajectories", tags=["trajectories"])


class LinkEventBody(BaseModel):
    event_seq: int = Field(..., ge=1)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    rationale: str | None = None
    actor: str = "user"


class RegisterTrajectoryBody(BaseModel):
    trajectory_id: str
    domain: str
    description: str
    parent: str | None = None
    competing_with: list[str] = Field(default_factory=list)
    status: str = "active"
    claim_status: str = "proposed"
    actor: str = "user"


@router.get("")
async def list_all():
    return {"trajectories": kernel_instance.kernel.list_trajectories()}


@router.get("/pending-links")
async def list_pending_links():
    """Proposed TrajectoryLinked edges awaiting user ratification."""
    pending: list[dict] = []
    for traj in kernel_instance.kernel.list_trajectories():
        tid = traj.get("id")
        if not tid:
            continue
        data = kernel_instance.kernel.query_trajectory(tid)
        if not data:
            continue
        for link in data.get("links", []):
            if link.get("claim_status") == "proposed":
                pending.append({**link, "trajectory_id": tid, "trajectory": data.get("registry")})
    return {"pending": pending}


@router.get("/{trajectory_id}")
async def get_trajectory(trajectory_id: str):
    data = kernel_instance.kernel.query_trajectory(trajectory_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return data


@router.post("/{trajectory_id}/links")
async def create_link(trajectory_id: str, body: LinkEventBody):
    if kernel_instance.kernel.query_trajectory(trajectory_id) is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    event = link_event(
        kernel_instance.kernel,
        trajectory_id,
        body.event_seq,
        actor=body.actor,
        confidence=body.confidence,
        rationale=body.rationale,
    )
    link_id = (event.payload or {}).get("link_id")
    return {"link_id": link_id, "event_seq": event.seq, "event_id": event.id}


@router.post("/register")
async def register(body: RegisterTrajectoryBody):
    event = register_trajectory(
        kernel_instance.kernel,
        body.trajectory_id,
        domain=body.domain,
        description=body.description,
        parent=body.parent,
        competing_with=body.competing_with,
        claim_status=body.claim_status,
        status=body.status,
        actor=body.actor,
    )
    return {"trajectory_id": body.trajectory_id, "event_seq": event.seq}


@router.post("/links/{link_id}/ratify")
async def ratify_link(link_id: str):
    link_authority.ratify(link_id, actor="user")
    return {"link_id": link_id, "claim_status": "ratified"}


@router.post("/links/{link_id}/reject")
async def reject_link(link_id: str, reason: str = ""):
    link_authority.reject(link_id, actor="user", reason=reason)
    return {"link_id": link_id, "claim_status": "rejected"}


@router.post("/{trajectory_id}/identity-opt-in")
async def identity_opt_in(trajectory_id: str):
    """Identity RFC P4 — user allows trajectory to influence identity narrative."""
    if kernel_instance.kernel.query_trajectory(trajectory_id) is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    identity_authority.opt_in(trajectory_id, actor="user")
    return {"trajectory_id": trajectory_id, "identity_narrative_opt_in": True}


# --- P2.3: Delta View API ---


@router.get("/{trajectory_id}/projection-delta")
async def projection_delta(trajectory_id: str, perspective: str | None = None):
    """Return the interpretation timeline for a trajectory.

    Shows how the meaning of this trajectory has evolved across different
    timestamps and perspectives.
    """
    data = compute_trajectory_delta(
        kernel_instance.kernel,
        trajectory_id,
        perspective=perspective,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return data


@router.post("/{trajectory_id}/identity-opt-out")
async def identity_opt_out(trajectory_id: str, reason: str = ""):
    if kernel_instance.kernel.query_trajectory(trajectory_id) is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    identity_authority.opt_out(trajectory_id, actor="user", reason=reason)
    return {"trajectory_id": trajectory_id, "identity_narrative_opt_in": False}

"""Trajectory Identity opt-in — Identity RFC P4 (per-trajectory, non-default)."""

from __future__ import annotations

from app.core.runtime import kernel_instance

_OPT_IN = "TrajectoryIdentityOptIn"
_OPT_OUT = "TrajectoryIdentityOptOut"


def _kernel():
    return kernel_instance.kernel


def opt_in(trajectory_id: str, actor: str = "user") -> None:
    """User allows this trajectory to influence Identity Projection narrative."""
    _kernel().emit_event(_OPT_IN, "trajectory", trajectory_id, actor=actor)


def opt_out(trajectory_id: str, actor: str = "user", reason: str = "") -> None:
    """Revoke identity-narrative influence for this trajectory."""
    payload = {"reason": reason} if reason else {}
    _kernel().emit_event(_OPT_OUT, "trajectory", trajectory_id, payload=payload, actor=actor)


def is_identity_opted_in(trajectory_id: str) -> bool:
    """Default False until user opts in (P4)."""
    events = _kernel().read_events(
        aggregate_type="trajectory",
        aggregate_id=trajectory_id,
        types=[_OPT_IN, _OPT_OUT],
        order="asc",
    )
    opted = False
    for event in events:
        if event.type == _OPT_IN:
            opted = True
        elif event.type == _OPT_OUT:
            opted = False
    return opted


def list_identity_opted_in(trajectory_ids: list[str] | None = None) -> list[str]:
    """Return trajectory ids currently opted in for identity narrative."""
    if trajectory_ids is None:
        from app.experimental.trajectory.engine import load_merged_registry

        trajectory_ids = list(load_merged_registry(_kernel()).keys())
    return [tid for tid in trajectory_ids if is_identity_opted_in(tid)]

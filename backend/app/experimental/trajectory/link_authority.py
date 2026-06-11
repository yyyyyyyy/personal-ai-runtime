"""Trajectory link authority — epistemic status for TrajectoryLinked edges."""

from __future__ import annotations

from app.core.runtime import kernel_instance

LINK_STATUS_EVENTS = frozenset({
    "TrajectoryLinkRatified",
    "TrajectoryLinkRejected",
    "TrajectoryLinkContested",
    "TrajectoryLinkReleased",
    "TrajectoryLinkReopened",
})


def _kernel():
    return kernel_instance.kernel


def ratify(link_id: str, actor: str = "user") -> None:
    _kernel().emit_event(
        "TrajectoryLinkRatified", "trajectory_link", link_id, actor=actor,
    )


def reject(link_id: str, actor: str = "user", reason: str = "") -> None:
    payload = {"reason": reason} if reason else {}
    _kernel().emit_event(
        "TrajectoryLinkRejected", "trajectory_link", link_id,
        payload=payload, actor=actor,
    )


def contest(link_id: str, actor: str = "user", reason: str = "") -> None:
    payload = {"reason": reason} if reason else {}
    _kernel().emit_event(
        "TrajectoryLinkContested", "trajectory_link", link_id,
        payload=payload, actor=actor,
    )


def release(link_id: str, actor: str = "user", reason: str = "") -> None:
    payload = {"reason": reason} if reason else {}
    _kernel().emit_event(
        "TrajectoryLinkReleased", "trajectory_link", link_id,
        payload=payload, actor=actor,
    )


def reopen(link_id: str, actor: str = "user") -> None:
    _kernel().emit_event(
        "TrajectoryLinkReopened", "trajectory_link", link_id, actor=actor,
    )

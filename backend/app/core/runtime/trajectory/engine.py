"""Trajectory engine — virtual query_trajectory from event_log + registry (Phase 1)."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.runtime.kernel.event import Event
from app.core.runtime.trajectory.registry import (
    load_yaml_registry,
    merge_registry_from_events,
)


def _event_dict(event: Event) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "id": event.id,
        "type": event.type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "actor": event.actor,
        "payload": event.payload,
        "caused_by": event.caused_by,
        "correlation_id": event.correlation_id,
        "ts": event.ts,
    }


LINK_STATUS_FROM_EVENT = {
    "TrajectoryLinkRatified": "ratified",
    "TrajectoryLinkRejected": "rejected",
    "TrajectoryLinkContested": "contested",
    "TrajectoryLinkReleased": "released",
    "TrajectoryLinkReopened": "contested",
}


def _new_link_id() -> str:
    return f"tlink_{uuid.uuid4().hex[:12]}"


def _resolve_link_status(kernel, link_id: str, initial: str = "proposed") -> str:
    events = kernel.read_events(
        aggregate_type="trajectory_link",
        aggregate_id=link_id,
        order="asc",
    )
    status = initial
    for event in events:
        if event.type in LINK_STATUS_FROM_EVENT:
            status = LINK_STATUS_FROM_EVENT[event.type]
    return status


def _collect_trajectory_links_virtual(kernel, trajectory_id: str) -> list[dict[str, Any]]:
    link_events = kernel.read_events(
        type="TrajectoryLinked",
        aggregate_type="trajectory",
        aggregate_id=trajectory_id,
        order="asc",
    )
    links: list[dict[str, Any]] = []
    for event in link_events:
        p = event.payload or {}
        link_id = p.get("link_id")
        if not link_id:
            continue
        initial = p.get("claim_status", "proposed")
        links.append({
            "link_id": link_id,
            "trajectory_id": trajectory_id,
            "event_seq": p.get("event_seq"),
            "actor": event.actor,
            "confidence": float(p.get("confidence", 0.5)),
            "claim_status": _resolve_link_status(kernel, link_id, initial),
            "rationale": p.get("rationale"),
            "linked_at_seq": event.seq,
            "linked_at": event.ts,
        })
    return links


def _collect_trajectory_links_materialized(kernel, trajectory_id: str) -> list[dict[str, Any]]:
    with kernel._db.get_db() as conn:
        rows = conn.execute(
            """SELECT link_id, trajectory_id, event_seq, claim_status, confidence,
                      rationale, actor, linked_at_seq, linked_at
               FROM trajectory_links
               WHERE trajectory_id = ?
               ORDER BY linked_at_seq ASC""",
            (trajectory_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _collect_trajectory_links(kernel, trajectory_id: str) -> list[dict[str, Any]]:
    """Phase 2 read path: materialized projection with virtual replay fallback."""
    materialized = _collect_trajectory_links_materialized(kernel, trajectory_id)
    if materialized:
        return materialized
    return _collect_trajectory_links_virtual(kernel, trajectory_id)


def rebuild_trajectory_links(kernel) -> int:
    """Replay TrajectoryLinked + link status events into trajectory_links."""
    from app.core.runtime.kernel import projectors

    link_events = kernel.read_events(type="TrajectoryLinked", order="asc")
    status_types = list(LINK_STATUS_FROM_EVENT.keys())
    status_events = kernel.read_events(types=status_types, order="asc")
    with kernel._db.get_db() as conn:
        conn.execute("DELETE FROM trajectory_links")
        for event in link_events:
            projectors.apply(event, conn)
        for event in status_events:
            projectors.apply(event, conn)
    return len(link_events) + len(status_events)


def load_merged_registry(kernel) -> dict[str, dict[str, Any]]:
    yaml_entries = load_yaml_registry()
    registered = kernel.read_events(type="TrajectoryRegistered", order="asc")
    return merge_registry_from_events(yaml_entries, registered)


def register_trajectory(
    kernel,
    trajectory_id: str,
    *,
    domain: str,
    description: str,
    parent: str | None = None,
    competing_with: list[str] | None = None,
    claim_status: str = "proposed",
    status: str = "active",
    perspective: str | None = None,
    actor: str = "system",
) -> Event:
    return kernel.emit_event(
        "TrajectoryRegistered",
        "trajectory",
        trajectory_id,
        payload={
            "domain": domain,
            "description": description,
            "parent": parent,
            "competing_with": competing_with or [],
            "claim_status": claim_status,
            "status": status,
            "perspective": perspective or domain,
        },
        actor=actor,
    )


def link_event(
    kernel,
    trajectory_id: str,
    event_seq: int,
    *,
    actor: str = "system",
    confidence: float = 0.5,
    rationale: str | None = None,
    claim_status: str = "proposed",
    caused_by: str | None = None,
) -> Event:
    link_id = _new_link_id()
    payload: dict[str, Any] = {
        "link_id": link_id,
        "event_seq": int(event_seq),
        "confidence": confidence,
        "claim_status": claim_status,
    }
    if rationale:
        payload["rationale"] = rationale
    return kernel.emit_event(
        "TrajectoryLinked",
        "trajectory",
        trajectory_id,
        payload=payload,
        actor=actor,
        caused_by=caused_by,
    )


def query_trajectory(kernel, trajectory_id: str) -> dict[str, Any] | None:
    """Virtual read model: registry + links + referenced events + competing ids."""
    registry = load_merged_registry(kernel)
    entry = registry.get(trajectory_id)
    if entry is None:
        return None

    links = _collect_trajectory_links(kernel, trajectory_id)
    event_seqs = [lnk["event_seq"] for lnk in links if lnk.get("event_seq") is not None]

    events = [
        _event_dict(event)
        for event in kernel.read_events_by_seqs(event_seqs)
    ]

    competing = list(entry.get("competing_with") or [])
    competing_entries = {
        cid: registry[cid]
        for cid in competing
        if cid in registry
    }

    return {
        "trajectory_id": trajectory_id,
        "registry": entry,
        "links": links,
        "events": events,
        "competing_with": competing,
        "competing": competing_entries,
    }


def list_trajectories(kernel) -> list[dict[str, Any]]:
    from app.core.runtime.trajectory.identity_authority import is_identity_opted_in

    registry = load_merged_registry(kernel)
    out: list[dict[str, Any]] = []
    for k, v in sorted(registry.items()):
        entry = dict(v, id=k)
        entry["identity_narrative_opt_in"] = is_identity_opted_in(k)
        out.append(entry)
    return out


def verify_competing_symmetry(registry: dict[str, dict[str, Any]]) -> list[str]:
    """V1: competing_with must be bidirectional."""
    violations: list[str] = []
    for tid, entry in registry.items():
        for other in entry.get("competing_with") or []:
            if other not in registry:
                violations.append(f"{tid}: competing_with references unknown {other!r}")
                continue
            reverse = registry[other].get("competing_with") or []
            if tid not in reverse:
                violations.append(
                    f"{tid} lists {other} as competing, but reverse link missing"
                )
    return violations

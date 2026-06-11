"""Trajectory Interpretation Delta — tracks how a Trajectory's meaning evolves over time.

Extracts interpretations from the Event Log that explain the same Trajectory
from the same Perspective at different timestamps. This powers the Delta View API
and Identity Projection contrast view.
"""

from __future__ import annotations

from typing import Any


def compute_trajectory_delta(
    kernel,
    trajectory_id: str,
    *,
    perspective: str | None = None,
) -> dict[str, Any] | None:
    """Compute the interpretation timeline for a trajectory.

    Scans TensionProposed, ClaimRevised, and MemoryDerived events referencing
    the trajectory to find how its meaning has been re-interpreted over time.

    Returns:
        {
            "trajectory_id": str,
            "perspective": str,
            "interpretations": [
                {"timestamp": str, "interpretation": str, "source": "system"|"user"}
            ]
        }
    """
    data = kernel.query_trajectory(trajectory_id)
    if data is None:
        return None

    registry = data.get("registry", {})
    traj_perspective = registry.get("perspective", registry.get("domain", "general"))

    if perspective and traj_perspective != perspective:
        return None

    # Gather all events that reference this trajectory
    event_seqs = [lnk["event_seq"] for lnk in data.get("links", []) if lnk.get("event_seq") is not None]
    if not event_seqs:
        return {
            "trajectory_id": trajectory_id,
            "perspective": traj_perspective,
            "interpretations": [],
        }

    # Find interpretation events: ClaimRevised, TensionProposed, and MemoryDerived
    # that reference the trajectory_id in their payload
    related = kernel.read_events(
        aggregate_type="memory",
        limit=500,
        order="asc",
    )

    interpretations: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in related:
        p = event.payload or {}
        content = p.get("content", "")
        if not content:
            continue

        # Check if this event references our trajectory
        traj_ref = p.get("trajectory_id") or (trajectory_id if trajectory_id in content else None)
        if not traj_ref or traj_ref != trajectory_id:
            continue

        claim_type = p.get("claim_type", "")
        timestamp = event.ts or ""
        source = "user" if event.actor == "user" else "system"
        key = f"{timestamp}|{content[:80]}"
        if key in seen:
            continue
        seen.add(key)

        if claim_type == "tension":
            interpretations.append({
                "timestamp": timestamp[:10],
                "interpretation": p.get("description", content[:100]),
                "source": source,
                "type": "tension",
            })
        elif event.type in ("ClaimRevised", "MemoryUpdated"):
            interpretations.append({
                "timestamp": timestamp[:10],
                "interpretation": content[:200],
                "source": source,
                "type": "revision",
            })

    # Add the trajectory description as the initial interpretation
    interpretations.insert(0, {
        "timestamp": data.get("links", [{}])[0].get("linked_at", "")[:10] if data.get("links") else "",
        "interpretation": registry.get("description", ""),
        "source": "system",
        "type": "registration",
    })

    interpretations.sort(key=lambda i: i["timestamp"])

    return {
        "trajectory_id": trajectory_id,
        "perspective": traj_perspective,
        "interpretations": interpretations,
    }

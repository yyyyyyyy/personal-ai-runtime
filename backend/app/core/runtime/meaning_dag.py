"""Interpretation Dependency DAG guards — MEANING_ONTOLOGY §3.2.

Forbidden upward generation:
  Claim/Pattern MUST NOT emit TrajectoryLinked
  Trajectory MUST NOT emit Belief
  Belief MUST NOT emit TrajectoryLinked
"""

from __future__ import annotations

from app.core.runtime.kernel.event import Event

# Layers that MUST NOT directly cause TrajectoryLinked emission.
_FORBIDDEN_TRAJECTORY_CAUSE_LAYERS = frozenset({"claim", "belief", "pattern"})

# Layers that MUST NOT directly cause Belief emission.
_FORBIDDEN_BELIEF_CAUSE_LAYERS = frozenset({"trajectory"})

# Payload keys suggesting upward generation into TrajectoryLinked.
_TRAJECTORY_UPWARD_PAYLOAD_KEYS = frozenset({
    "source_belief_id",
    "source_pattern_id",
    "derived_from_belief",
    "from_pattern",
    "from_belief",
    "generated_from_pattern",
})

# Payload keys suggesting Trajectory emitted Belief (not cite-down evidence).
_BELIEF_UPWARD_PAYLOAD_KEYS = frozenset({
    "generated_from_trajectory",
    "source_trajectory_id",
    "from_trajectory",
})


def classify_meaning_layer(event: Event) -> str | None:
    """Classify event into Meaning layer for DAG checks."""
    t = event.type
    p = event.payload or {}

    if t in ("TrajectoryLinked", "TrajectoryRegistered"):
        return "trajectory"
    if t == "BeliefFormed":
        return "belief"
    if t == "PatternDetected":
        return "pattern"
    if t in ("MemoryDerived", "MemoryUpdated"):
        origin = p.get("origin", "")
        belief_type = p.get("belief_type", "")
        if origin == "claim" or belief_type == "claim":
            return "claim"
        if origin == "belief" or belief_type == "belief":
            return "belief"
        return "representation"
    return None


def _resolve_caused_by(
    event: Event,
    by_id: dict[str, Event],
) -> Event | None:
    if not event.caused_by:
        return None
    return by_id.get(event.caused_by)


def audit_meaning_dag(events: list[Event]) -> tuple[list[str], list[str]]:
    """Return (failures, warnings) for event log against §3.2."""
    failures: list[str] = []
    warnings: list[str] = []

    by_id = {e.id: e for e in events if e.id}

    for event in events:
        p = event.payload or {}

        if event.type == "TrajectoryLinked":
            cause = _resolve_caused_by(event, by_id)
            if cause is not None:
                cause_layer = classify_meaning_layer(cause)
                if cause_layer in _FORBIDDEN_TRAJECTORY_CAUSE_LAYERS:
                    failures.append(
                        f"DAG: TrajectoryLinked seq={event.seq} caused_by "
                        f"{cause.type}({cause_layer}) — upward generation"
                    )
            for key in _TRAJECTORY_UPWARD_PAYLOAD_KEYS:
                if key in p:
                    failures.append(
                        f"DAG: TrajectoryLinked seq={event.seq} payload.{key} "
                        f"— forbidden upward source"
                    )
            source_type = p.get("source_type")
            if source_type in ("claim", "belief", "pattern"):
                failures.append(
                    f"DAG: TrajectoryLinked seq={event.seq} source_type={source_type!r}"
                )

        if event.type == "BeliefFormed":
            cause = _resolve_caused_by(event, by_id)
            if cause is not None:
                cause_layer = classify_meaning_layer(cause)
                if cause_layer in _FORBIDDEN_BELIEF_CAUSE_LAYERS:
                    failures.append(
                        f"DAG: BeliefFormed seq={event.seq} caused_by "
                        f"{cause.type}({cause_layer}) — Trajectory must not emit Belief"
                    )
            for key in _BELIEF_UPWARD_PAYLOAD_KEYS:
                if key in p and key != "evidence_chain":
                    val = p.get(key)
                    if key == "source_trajectory_id" and isinstance(
                        p.get("evidence_chain"), dict
                    ):
                        # cite-down via evidence_chain is allowed
                        continue
                    if val:
                        failures.append(
                            f"DAG: BeliefFormed seq={event.seq} payload.{key} "
                            f"— forbidden upward generation"
                        )

        if event.type == "PatternDetected":
            cause = _resolve_caused_by(event, by_id)
            if cause is not None and classify_meaning_layer(cause) == "trajectory":
                warnings.append(
                    f"DAG: PatternDetected seq={event.seq} caused_by trajectory event "
                    f"— verify not aggregated from Trajectory alone"
                )

    return failures, warnings


def audit_kernel_event_log(kernel) -> tuple[list[str], list[str]]:
    """Audit full kernel event log."""
    events = kernel.read_events(order="asc")
    return audit_meaning_dag(events)

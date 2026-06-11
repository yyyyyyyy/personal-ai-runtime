"""Trajectory Registry — continuity hypotheses from YAML + TrajectoryRegistered events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import settings


def default_registry_path() -> Path:
    return Path(settings.trajectory_registry_path)


def load_yaml_registry(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load trajectory definitions from YAML. Returns id -> entry."""
    path = path or default_registry_path()
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries: dict[str, dict[str, Any]] = {}
    for item in data.get("trajectories", []):
        tid = item.get("id")
        if tid:
            entries[tid] = dict(item)
            # Ensure perspective defaults to domain if not set
            if "perspective" not in entries[tid]:
                entries[tid]["perspective"] = entries[tid].get("domain", "general")
    return entries


def merge_registry_from_events(
    yaml_entries: dict[str, dict[str, Any]],
    registered_events: list[Any],
) -> dict[str, dict[str, Any]]:
    """Overlay TrajectoryRegistered events onto YAML (event wins on conflict)."""
    merged = {k: dict(v) for k, v in yaml_entries.items()}
    for event in registered_events:
        tid = event.aggregate_id
        p = event.payload or {}
        merged[tid] = {
            "id": tid,
            "domain": p.get("domain", merged.get(tid, {}).get("domain", "general")),
            "perspective": p.get("perspective", merged.get(tid, {}).get("perspective", p.get("domain", "general"))),
            "description": p.get("description", merged.get(tid, {}).get("description", "")),
            "status": p.get("status", merged.get(tid, {}).get("status", "active")),
            "claim_status": p.get("claim_status", merged.get(tid, {}).get("claim_status", "proposed")),
            "parent": p.get("parent", merged.get(tid, {}).get("parent")),
            "competing_with": p.get(
                "competing_with",
                merged.get(tid, {}).get("competing_with", []),
            ),
        }
    return merged


def list_trajectory_ids(registry: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(registry.keys())

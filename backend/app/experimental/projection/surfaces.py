"""Load identity_surfaces.yaml and agency_surfaces.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import settings


def _default_identity_path() -> Path:
    return Path(settings.identity_surfaces_path)


def _default_agency_path() -> Path:
    return Path(settings.agency_surfaces_path)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 0, "surfaces": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"surfaces": []}


def load_identity_surfaces(path: Path | None = None) -> list[dict[str, Any]]:
    data = _load_yaml(path or _default_identity_path())
    return list(data.get("surfaces") or [])


def load_agency_surfaces(path: Path | None = None) -> list[dict[str, Any]]:
    data = _load_yaml(path or _default_agency_path())
    return list(data.get("surfaces") or [])


def identity_surface_ids() -> set[str]:
    return {s["id"] for s in load_identity_surfaces() if s.get("id")}

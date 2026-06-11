"""Agency surface static lint — G5: forbidden Meaning inputs in ranking modules."""

from __future__ import annotations

import re
from pathlib import Path

from app.experimental.projection.surfaces import load_agency_surfaces

# Map module path to repo-relative file path
_MODULE_FILES: dict[str, str] = {
    "app.product.morning_brief": "app/product/morning_brief.py",
    "app.api.goals": "app/api/goals.py",
}

# Source patterns that suggest Meaning → Agency leak
_FORBIDDEN_SOURCE_PATTERNS = [
    re.compile(r'query_state\s*\(\s*["\']memories["\']'),
    re.compile(r"origin\s*=\s*['\"]claim['\"]"),
    re.compile(r"claim_authority"),
    re.compile(r"list_actionable_claims"),
    re.compile(r"query_trajectory"),
    re.compile(r"belief_engine"),
    re.compile(r'query_state\s*\(\s*["\']patterns["\']'),
]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_module_path(module: str) -> Path | None:
    rel = _MODULE_FILES.get(module)
    if rel:
        path = _backend_root() / rel
        return path if path.is_file() else None
    # fallback: app.foo.bar -> app/foo/bar.py
    parts = module.split(".")
    if parts[0] != "app":
        return None
    candidate = _backend_root() / "/".join(parts[:-1]) / f"{parts[-1]}.py"
    return candidate if candidate.is_file() else None


def lint_agency_surface_source(
    module: str,
    forbidden: list[str] | None = None,
) -> list[str]:
    """Return violation messages for a single agency surface module."""
    path = _resolve_module_path(module)
    if path is None:
        return [f"WARN: cannot resolve module file for {module!r}"]

    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for pat in _FORBIDDEN_SOURCE_PATTERNS:
        if pat.search(text):
            violations.append(f"FAIL:{module}: forbidden pattern {pat.pattern!r} in {path.name}")

    if forbidden:
        for item in forbidden:
            glob = item.rstrip(".*")
            if glob and glob in text:
                violations.append(f"FAIL:{module}: forbidden token {item!r} in source")

    return violations


def lint_all_agency_surfaces() -> list[str]:
    violations: list[str] = []
    for surface in load_agency_surfaces():
        module = surface.get("module", "")
        forbidden = surface.get("rank_inputs_forbidden") or []
        violations.extend(lint_agency_surface_source(module, forbidden))
    return violations

#!/usr/bin/env python
"""Verify release version is consistent across authoritative sources.

Authoritative: backend/app/version.py (VERSION).
Also checked: repo-root VERSION, frontend/package.json, desktop/package.json,
.env.example header, docs/README.md version line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _read_authoritative_version() -> str:
    version_py = BACKEND_DIR / "app" / "version.py"
    text = version_py.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse VERSION from {version_py}")
    return match.group(1)


def _check_version_file(expected: str) -> list[str]:
    path = REPO_ROOT / "VERSION"
    if not path.is_file():
        return [f"Missing {path.relative_to(REPO_ROOT)}"]
    actual = path.read_text(encoding="utf-8").strip()
    if actual != expected:
        return [f"{path.relative_to(REPO_ROOT)}: expected {expected!r}, got {actual!r}"]
    return []


def _check_package_json(path: Path, expected: str) -> list[str]:
    if not path.is_file():
        return [f"Missing {path.relative_to(REPO_ROOT)}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    actual = data.get("version", "")
    if actual != expected:
        return [f"{path.relative_to(REPO_ROOT)}: expected version {expected!r}, got {actual!r}"]
    return []


def _check_env_example(expected: str) -> list[str]:
    path = REPO_ROOT / ".env.example"
    if not path.is_file():
        return [f"Missing {path.relative_to(REPO_ROOT)}"]
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    expected_line = f"# Personal AI Runtime v{expected}"
    if first_line.strip() != expected_line:
        return [
            f".env.example first line: expected {expected_line!r}, got {first_line.strip()!r}"
        ]
    return []


def _check_docs_readme(expected: str) -> list[str]:
    path = REPO_ROOT / "docs" / "README.md"
    if not path.is_file():
        return [f"Missing {path.relative_to(REPO_ROOT)}"]
    text = path.read_text(encoding="utf-8")
    if f"`{expected}`" not in text:
        return [f"docs/README.md: expected version `{expected}` in current-version line"]
    return []


def main() -> int:
    expected = _read_authoritative_version()
    errors: list[str] = []
    errors.extend(_check_version_file(expected))
    errors.extend(_check_package_json(REPO_ROOT / "frontend" / "package.json", expected))
    errors.extend(_check_package_json(REPO_ROOT / "desktop" / "package.json", expected))
    errors.extend(_check_env_example(expected))
    errors.extend(_check_docs_readme(expected))

    if errors:
        print("Version sync check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: version {expected} consistent across all checked sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())

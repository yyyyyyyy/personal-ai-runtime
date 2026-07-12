#!/usr/bin/env python3
"""Ensure project runtime dependencies match the canonical requirements.txt.

Also validates that requirements.lock is present and covers every exact pin
from requirements.txt / requirements-dev.txt. This check must run *before*
``pip install --require-hashes -r requirements.lock`` and therefore must not
depend on pip-tools being installed.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
import tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = BACKEND_DIR / "requirements.txt"
DEV_REQUIREMENTS_PATH = BACKEND_DIR / "requirements-dev.txt"
LOCK_PATH = BACKEND_DIR / "requirements.lock"
PYPROJECT_PATH = BACKEND_DIR / "pyproject.toml"
EXACT_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[A-Za-z0-9._,-]+\])?"
    r"==(?P<version>[^<>=!~;\s]+)(?:\s*;\s*.+)?$"
)
LOCK_PACKAGE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?==(?P<version>[^\s\\;]+)",
    re.IGNORECASE,
)
INPUT_HASH_PREFIX = "# input-sha256 "
PLATFORM_ONLY_LOCK_BLOCKS = {
    # pip-compile evaluates markers for the host platform and omits this
    # Windows-only Uvicorn dependency when the canonical lock is generated on
    # macOS/Linux. Hashes are from the colorama 0.4.6 PyPI release.
    "colorama": """colorama==0.4.6 ; sys_platform == "win32" \\
    --hash=sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44 \\
    --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6
    # via
    #   -r requirements.txt
    #   uvicorn
""",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements_dependencies(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and not line.lstrip().startswith(
            ("#", "-r ", "--requirement ", "-e ", "--extra-index-url", "--index-url")
        )
    ]


def _pyproject_dependencies() -> list[str]:
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    return list(pyproject["project"]["dependencies"])


def _lock_packages() -> dict[str, str]:
    """Map normalized package name → pinned version from requirements.lock."""
    packages: dict[str, str] = {}
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        match = LOCK_PACKAGE.match(line.strip())
        if match:
            packages[_normalize_name(match.group("name"))] = match.group("version")
    return packages


def _input_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (REQUIREMENTS_PATH, DEV_REQUIREMENTS_PATH)
    }


def _stamp_lock_input_hashes() -> None:
    """Record the exact dependency inputs used to generate requirements.lock."""
    text = LOCK_PATH.read_text(encoding="utf-8")
    locked_names = set(_lock_packages())
    missing_platform_blocks = [
        block
        for name, block in PLATFORM_ONLY_LOCK_BLOCKS.items()
        if name not in locked_names
    ]
    if missing_platform_blocks:
        text = text.rstrip() + "\n" + "\n".join(missing_platform_blocks)
    body = "\n".join(
        line for line in text.splitlines()
        if not line.startswith(INPUT_HASH_PREFIX)
    )
    markers = "\n".join(
        f"{INPUT_HASH_PREFIX}{name}={digest}"
        for name, digest in _input_hashes().items()
    )
    LOCK_PATH.write_text(f"{markers}\n{body}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stamp-lock",
        action="store_true",
        help="stamp requirements.lock with hashes of its exact input files",
    )
    args = parser.parse_args(argv)

    if args.stamp_lock:
        if not LOCK_PATH.is_file():
            print("requirements.lock is missing", file=sys.stderr)
            return 1
        _stamp_lock_input_hashes()

    expected = _requirements_dependencies(REQUIREMENTS_PATH)
    actual = _pyproject_dependencies()
    errors: list[str] = []

    for path, dependencies in (
        (REQUIREMENTS_PATH, expected),
        (DEV_REQUIREMENTS_PATH, _requirements_dependencies(DEV_REQUIREMENTS_PATH)),
    ):
        for dependency in dependencies:
            if not EXACT_REQUIREMENT.fullmatch(dependency):
                errors.append(f"{path.name}: dependency is not an exact pin: {dependency!r}")

    if actual != expected:
        errors.append("pyproject.toml dependencies differ from requirements.txt")

    # Verify requirements-dev.txt starts with "-r requirements.txt".
    dev_lines = DEV_REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
    if not dev_lines or not any(
        line.strip().startswith("-r requirements.txt") for line in dev_lines[:5]
    ):
        errors.append("requirements-dev.txt must include '-r requirements.txt'")

    if not LOCK_PATH.is_file():
        errors.append("requirements.lock is missing — run 'make lockfile'")
    else:
        lock_text = LOCK_PATH.read_text(encoding="utf-8")
        if "--hash=" not in lock_text:
            errors.append("requirements.lock has no --hash entries")
        expected_hashes = _input_hashes()
        stamped_hashes: dict[str, str] = {}
        for line in lock_text.splitlines():
            if not line.startswith(INPUT_HASH_PREFIX):
                continue
            name, separator, digest = line[len(INPUT_HASH_PREFIX):].partition("=")
            if separator:
                stamped_hashes[name] = digest
        for name, digest in expected_hashes.items():
            if stamped_hashes.get(name) != digest:
                errors.append(
                    f"requirements.lock is stale for {name} — run 'make lockfile'"
                )
        lock_packages = _lock_packages()
        for path in (REQUIREMENTS_PATH, DEV_REQUIREMENTS_PATH):
            for dependency in _requirements_dependencies(path):
                match = EXACT_REQUIREMENT.fullmatch(dependency)
                if not match:
                    continue
                name = _normalize_name(match.group("name"))
                version = match.group("version")
                locked = lock_packages.get(name)
                if locked is None:
                    errors.append(f"requirements.lock missing package {name}=={version}")
                elif locked != version:
                    errors.append(
                        f"requirements.lock has {name}=={locked}, expected {version}"
                    )

    if errors:
        print(
            "Dependency sync check FAILED: backend/requirements.txt is authoritative.",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        if actual != expected:
            diff = difflib.unified_diff(
                actual,
                expected,
                fromfile="pyproject.toml [project].dependencies",
                tofile="requirements.txt",
                lineterm="",
            )
            for line in diff:
                print(line, file=sys.stderr)
        return 1

    print(
        "OK: dependency inputs use exact pins, pyproject.toml matches "
        "requirements.txt, and requirements.lock matches the stamped inputs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

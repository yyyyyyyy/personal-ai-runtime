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
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9._,-]+)\])?"
    r"==(?P<version>[^<>=!~;\s]+)"
    r"(?:\s*;\s*(?P<marker>.+))?$"
)
LOCK_PACKAGE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[^\]]+)\])?"
    r"==(?P<version>[^\s\\;]+)"
    r"(?:\s*;\s*(?P<marker>.+?))?\s*(?:\\)?$",
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
    # humanfriendly (via coloredlogs → onnxruntime/chromadb) pulls this on
    # Windows only; pip-compile on macOS/Linux omits it and --require-hashes
    # then fails when pip resolves the unpinned transitive wheel.
    "pyreadline3": """pyreadline3==3.5.6 ; sys_platform == "win32" \\
    --hash=sha256:8449b734232e42a5dcd74048e39b60db2839a4c38cf3ae2bf7707d58b5389c0d
    # via humanfriendly
""",
    # mcp declares pywin32>=310 on Windows; pip-compile on macOS/Linux omits it.
    "pywin32": """pywin32==312 ; sys_platform == "win32" \\
    --hash=sha256:772235332b5d1024c696f11cea1ae4be7930f0a8b894bb43db14e3f435f1ff7e \\
    --hash=sha256:5dbc35d2b5320dc07f25fa31269cfb767471002b17de5eb067d03da68c7cb2db \\
    --hash=sha256:17948aeadbdb091f0ced6ef0841620794e68327b94ee415571c1203594b7215c \\
    --hash=sha256:d11417d84412f859b722fad0841b3614459ed0047f7542d8362e77884f6b6e8a \\
    --hash=sha256:dab4f65ac9c4e48400a2a0530c46c3c579cd5905ecd11b80692373915269208b \\
    --hash=sha256:b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc \\
    --hash=sha256:7a27df850933d16a8eabfbaeb73d52b273e2da667f80d70b01a89d1f6828d02c \\
    --hash=sha256:c53e878d15a1c44788082bfe712a905433473aa38f86375b7cf8b45e3acbaaf9 \\
    --hash=sha256:d620900033cc7531e50727c3c8333091df5dd3ffe6d68cdca38c03f5821408d5 \\
    --hash=sha256:dc90147579a905b8635e1b0ec6514967dcb07e6e0d9c42f1477feef14cac23bb
    # via mcp
""",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _normalize_extras(extras: str | None) -> tuple[str, ...]:
    if not extras:
        return ()
    return tuple(sorted(part.strip().lower() for part in extras.split(",") if part.strip()))


def _normalize_marker(marker: str | None) -> str:
    if not marker:
        return ""
    # pip-compile rewrites quote style; compare on a quote-insensitive form.
    normalized = " ".join(marker.strip().rstrip("\\").split())
    return normalized.replace('"', "'")


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


def _lock_packages() -> dict[str, dict[str, object]]:
    """Map normalized package name → version/extras/marker from requirements.lock."""
    packages: dict[str, dict[str, object]] = {}
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        match = LOCK_PACKAGE.match(line.strip())
        if not match:
            continue
        name = _normalize_name(match.group("name"))
        packages[name] = {
            "version": match.group("version"),
            "extras": _normalize_extras(match.group("extras")),
            "marker": _normalize_marker(match.group("marker")),
        }
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
                extras = _normalize_extras(match.group("extras"))
                marker = _normalize_marker(match.group("marker"))
                locked = lock_packages.get(name)
                if locked is None:
                    errors.append(f"requirements.lock missing package {name}=={version}")
                    continue
                if locked["version"] != version:
                    errors.append(
                        f"requirements.lock has {name}=={locked['version']}, "
                        f"expected {version}"
                    )
                if locked["extras"] != extras:
                    errors.append(
                        f"requirements.lock extras for {name} are "
                        f"{locked['extras']!r}, expected {extras!r} — run 'make lockfile'"
                    )
                if locked["marker"] != marker:
                    errors.append(
                        f"requirements.lock marker for {name} is "
                        f"{locked['marker']!r}, expected {marker!r} — run 'make lockfile'"
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

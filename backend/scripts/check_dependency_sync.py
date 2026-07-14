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
    # huggingface-hub requires hf-xet on x86_64/arm64, but the marker compares
    # platform_machine to lowercase "amd64" while Windows reports "AMD64", so
    # pip-compile on Windows omits it and Linux/macOS --require-hashes then fails.
    "hf-xet": """hf-xet==1.5.1 \\
    --hash=sha256:0c97106032ef70467b4f6bc2d0ccc266d7613ee076afc56516c502f87ce1c4a6 \\
    --hash=sha256:3474760d10e3bb6f92ff3f024fcb00c0b3e4001e9b035c7483e49a5dd17aa70f \\
    --hash=sha256:4f561cbbb92f80960772059864b7fb07eae879adde1b2e781ec6f86f6ac26c59 \\
    --hash=sha256:51ef4500dab3764b41135ee1381a4b62ce56fc54d4c92b719b59e597d6df5bf6 \\
    --hash=sha256:6071d5ccb4d8d2cbd5fea5cc798da4f0ba3f44e25369591c4e89a4987050e61d \\
    --hash=sha256:6208adb15d192b90e4c2ad2a27ed864359b2cb0f2494eb6d7c7f3699ac02e2bf \\
    --hash=sha256:6762d89b9e3267dfd502b29b2a327b4525f33b17e7b509a78d94e2151a30ce30 \\
    --hash=sha256:6abd35c3221eff63836618ddfb954dcf84798603f71d8e33e3ed7b04acfdbe6e \\
    --hash=sha256:6f7a04a8ad962422e225bc49fbbac99dc1806764b1f3e54dbd154bffa7593947 \\
    --hash=sha256:8298485c1e36e7e67cbd01eeb1376619b7af43d4f1ec245caae306f890a8a32d \\
    --hash=sha256:892e3a3a3aecc12aded8b93cf4f9cd059282c7de0732f7d55026f3abdf474350 \\
    --hash=sha256:93d090b57b211133f6c0dab0205ef5cb6d89162979ba75a74845045cc3063b8e \\
    --hash=sha256:94e761bbd266bf4c03cee73753916062665ce8365aa40ed321f45afcb934b41e \\
    --hash=sha256:97f212a88d14bbf573619a74b7fecb238de77d08fc702e54dec6f78276ca3283 \\
    --hash=sha256:a93df2039190502835b1db8cd7e178b0b7b889fe9ab51299d5ced26e0dd879a4 \\
    --hash=sha256:bf67e6ed10260cef62e852789dc91ebb03f382d5bdc4b1dbeb64763ea275e7d6 \\
    --hash=sha256:c6b6cd08ca095058780b50b8ce4d6cbf6787bcf27841705d58a9d32246e3e47a \\
    --hash=sha256:d48199c2bf4f8df0adc55d31d1368b6ec0e4d4f45bc86b08038089c23db0bed8 \\
    --hash=sha256:dbf48c0d02cf0b2e568944330c60d9120c272dabe013bd892d48e25bc6797577 \\
    --hash=sha256:e1af0de8ca6f190d4294a28b88023db64a1e2d1d719cab044baf75bec569e7a9 \\
    --hash=sha256:e78e4e5192ad2b674c2e1160b651cb9134db974f8ae1835bdfbfb0166b894a43 \\
    --hash=sha256:e7dbb40617410f432182d918e37c12303fe6700fd6aa6c5964e30a535a4461d6 \\
    --hash=sha256:f4ad3ebd4c32dd2b27099d69dc7b2df821e30767e46fb6ee6a0713778243b8ff \\
    --hash=sha256:f61e3665892a6c8c5e765395838b8ddf36185da835253d4bc4509a81e49fb342 \\
    --hash=sha256:f7b3002f95d1c13e24bcb4537baa8f0eb3838957067c91bb4959bc004a6435f5
    # via huggingface-hub
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


def _platform_block_header(block: str) -> tuple[str, str]:
    """Return (normalized_name, expected_marker) from a platform-only lock block."""
    first_line = block.strip().splitlines()[0]
    match = LOCK_PACKAGE.match(first_line)
    if not match:
        raise ValueError(f"invalid PLATFORM_ONLY_LOCK_BLOCKS header: {first_line!r}")
    return _normalize_name(match.group("name")), _normalize_marker(match.group("marker"))


def _rewrite_lock_package_header(text: str, name: str, new_header: str) -> str:
    """Replace the ``name==...`` header line; leave hash / via lines intact."""
    header = new_header.rstrip()
    if not header.endswith("\\"):
        header = f"{header} \\"
    out: list[str] = []
    replaced = False
    for line in text.splitlines():
        match = LOCK_PACKAGE.match(line.strip())
        if (
            not replaced
            and match
            and _normalize_name(match.group("name")) == name
        ):
            out.append(header)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        raise ValueError(f"package {name!r} not found in requirements.lock")
    ending = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + ending


def _stamp_lock_input_hashes() -> None:
    """Record the exact dependency inputs used to generate requirements.lock.

    Also ensures Windows-only transitive pins carry ``sys_platform == \"win32\"``.
    pip-compile on Windows emits those packages without markers; without this
    rewrite, Linux CI tries to install pywin32/pyreadline3 and fails.
    """
    text = LOCK_PATH.read_text(encoding="utf-8")
    locked = _lock_packages()
    missing_platform_blocks: list[str] = []
    for name, block in PLATFORM_ONLY_LOCK_BLOCKS.items():
        first_line = block.strip().splitlines()[0]
        _, expected_marker = _platform_block_header(block)
        locked_pkg = locked.get(name)
        if locked_pkg is None:
            missing_platform_blocks.append(block)
        elif locked_pkg["marker"] != expected_marker:
            text = _rewrite_lock_package_header(text, name, first_line)
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
        for name, block in PLATFORM_ONLY_LOCK_BLOCKS.items():
            _, expected_marker = _platform_block_header(block)
            locked = lock_packages.get(name)
            if locked is None:
                errors.append(
                    f"requirements.lock missing platform-only package {name} "
                    "— run 'make lockfile'"
                )
            elif locked["marker"] != expected_marker:
                errors.append(
                    f"requirements.lock marker for {name} is "
                    f"{locked['marker']!r}, expected {expected_marker!r} "
                    "— run 'make lockfile'"
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

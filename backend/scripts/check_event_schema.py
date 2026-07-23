"""Event payload schema_version Contract gate.

Ensures every declared ``EVENT_*`` type has a recorded schema version and that
the map does not drift silently. Kernel ``emit_event`` stamps
``payload[\"schema_version\"]`` from this registry.

Usage:
    python -m scripts.check_event_schema
    python -m scripts.check_event_schema --snapshot
    python -m scripts.check_event_schema --record
    python -m scripts.check_event_schema --record --allow-downgrade
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()

ROOT = Path(__file__).resolve().parent.parent.parent
CONSTANTS = (
    ROOT / "backend" / "app" / "core" / "runtime" / "kernel" / "constants.py"
)
BASELINE_PATH = (
    Path(__file__).resolve().parent / "baselines" / "event_schema_versions.json"
)

_EVENT_ASSIGN_RE = re.compile(r'^EVENT_[A-Z0-9_]+\s*=\s*"([^"]+)"', re.MULTILINE)


def parse_declared_event_types(text: str | None = None) -> list[str]:
    raw = text if text is not None else CONSTANTS.read_text(encoding="utf-8")
    types = sorted(set(_EVENT_ASSIGN_RE.findall(raw)))
    return types


def load_overrides() -> dict[str, int]:
    from app.core.runtime.kernel.constants import (
        EVENT_SCHEMA_VERSION_DEFAULT,
        EVENT_SCHEMA_VERSION_OVERRIDES,
    )

    return {
        "default": int(EVENT_SCHEMA_VERSION_DEFAULT),
        "overrides": {
            str(k): int(v) for k, v in EVENT_SCHEMA_VERSION_OVERRIDES.items()
        },
    }


def compute_versions() -> dict[str, int]:
    from app.core.runtime.kernel.constants import event_schema_version

    return {t: int(event_schema_version(t)) for t in parse_declared_event_types()}


def load_baseline() -> dict[str, object]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def baseline_versions(data: dict[str, object]) -> dict[str, int]:
    raw = data.get("versions") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items()}


def build_baseline_doc(versions: dict[str, int]) -> dict[str, object]:
    from app.core.runtime.kernel.constants import PAYLOAD_SCHEMA_VERSION_KEY

    meta = load_overrides()
    return {
        "schema_version_key": PAYLOAD_SCHEMA_VERSION_KEY,
        "default_version": meta["default"],
        "versions": dict(sorted(versions.items())),
    }


def find_downgrades(
    current: dict[str, int],
    baseline: dict[str, int],
) -> list[tuple[str, int, int]]:
    """Return ``(type, baseline_ver, current_ver)`` where current < baseline."""
    out: list[tuple[str, int, int]] = []
    for etype, base_ver in baseline.items():
        if etype in current and current[etype] < base_ver:
            out.append((etype, base_ver, current[etype]))
    return sorted(out)


def record_baseline(
    versions: dict[str, int],
    *,
    allow_downgrade: bool = False,
    verbose: bool = True,
) -> int:
    """Write baseline. Rejects version downgrades unless ``allow_downgrade``."""
    baseline = baseline_versions(load_baseline())
    downgrades = find_downgrades(versions, baseline)
    if downgrades and not allow_downgrade:
        if verbose:
            print("  [FAIL] refusing to record schema version downgrade(s):")
            for etype, base_ver, cur_ver in downgrades:
                print(f"    {etype}: baseline={base_ver} current={cur_ver}")
            print("    Re-bump overrides, or pass --allow-downgrade intentionally.")
        return 1

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = build_baseline_doc(versions)
    BASELINE_PATH.write_text(
        json.dumps(doc, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    if verbose:
        print(f"Recorded {len(versions)} event schema version(s) → {BASELINE_PATH}")
    return 0


def check(*, verbose: bool = True) -> int:
    current = compute_versions()
    baseline = baseline_versions(load_baseline())
    meta = load_overrides()
    overrides: dict[str, int] = meta["overrides"]  # type: ignore[assignment]

    violations = 0

    # Overrides must name declared event types and stay >= 1.
    declared = set(current)
    for etype, ver in sorted(overrides.items()):
        if etype not in declared:
            violations += 1
            if verbose:
                print(f"  [FAIL] override for unknown event type: {etype}")
        if ver < 1:
            violations += 1
            if verbose:
                print(f"  [FAIL] {etype}: override version {ver} < 1")

    if not baseline:
        violations += 1
        if verbose:
            print(
                f"  [FAIL] missing baseline at {BASELINE_PATH.relative_to(ROOT)} "
                "(run with --record)"
            )
        return 1

    if current != baseline:
        violations += 1
        if verbose:
            only_cur = sorted(set(current) - set(baseline))
            only_base = sorted(set(baseline) - set(current))
            changed = sorted(
                t for t in set(current) & set(baseline)
                if current[t] != baseline[t]
            )
            print("  [FAIL] event schema version map drifted from baseline")
            if only_cur:
                print(f"    added types: {only_cur}")
            if only_base:
                print(f"    removed types: {only_base}")
            for t in changed:
                print(f"    {t}: baseline={baseline[t]} current={current[t]}")
                if current[t] < baseline[t]:
                    print("      (version downgrade is forbidden)")
            print(
                f"    Update intentionally, then: "
                f"python -m scripts.check_event_schema --record"
            )

    if verbose and violations == 0:
        print(
            f"EVENT SCHEMA OK — {len(current)} event type(s), "
            f"default_version={meta['default']}"
        )
    return 1 if violations else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print computed type→version map and exit 0",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write current map to the baseline file",
    )
    parser.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="With --record, allow persisting a lower schema version",
    )
    args = parser.parse_args(argv)

    versions = compute_versions()
    if args.snapshot:
        print(json.dumps(build_baseline_doc(versions), indent=2))
        return 0
    if args.record:
        return record_baseline(
            versions,
            allow_downgrade=args.allow_downgrade,
            verbose=True,
        )
    return check(verbose=True)


if __name__ == "__main__":
    sys.exit(main())

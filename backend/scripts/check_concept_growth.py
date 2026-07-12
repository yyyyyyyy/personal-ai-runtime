"""Architecture Contract Gate — enforces the Runtime Algebra evolution contract.

Reads the current concept baseline from ``runtime-algebra.md`` §4.6 and
fails if any tracked metric has grown since the last recorded baseline.

This script is the CI enforcement of the Concept Compression Contract
(§5.2). When you intentionally reduce a metric, update the baseline AND
the table in docs/02-concepts/runtime-algebra.md §4.6.

Usage:
    python scripts/check_concept_growth.py            # check against baseline
    python scripts/check_concept_growth.py --snapshot # print current values
    python scripts/check_concept_growth.py --strict   # also fail on non-zero dead_code_files
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# ── Measurers ────────────────────────────────────────────────────────────────

def count_runtime_files() -> int:
    """Count .py files under backend/app/core/runtime/ (recursive)."""
    runtime_dir = ROOT / "backend" / "app" / "core" / "runtime"
    return len(list(runtime_dir.rglob("*.py")))


def count_event_types() -> int:
    """Count individual ``EVENT_* = \"...\"`` string assignments in constants.py."""
    constants = ROOT / "backend" / "app" / "core" / "runtime" / "kernel" / "constants.py"
    text = constants.read_text()
    # Only match string-valued EVENT_* = "..." — exclude frozenset/set assignments
    return len(re.findall(r"EVENT_[A-Z_]+\s*=\s*\"", text))


def count_query_state_selectors() -> int:
    """Count ``if selector ==`` branches in kernel_query_state.py."""
    query_state = ROOT / "backend" / "app" / "core" / "runtime" / "kernel" / "kernel_query_state.py"
    text = query_state.read_text()
    return len(re.findall(r'if\s+selector\s*==\s*"', text))


def count_fragments() -> int:
    """Count fragment class registrations in fragments/register.py."""
    reg = ROOT / "backend" / "app" / "fragments" / "register.py"
    text = reg.read_text()
    # Count class names in _ALL_FRAGMENT_CLASSES list
    match = re.search(r"_ALL_FRAGMENT_CLASSES\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return -1
    return len(re.findall(r"\b\w+Fragment\b", match.group(1)))


def count_governed_tables() -> int:
    """Count tables in GOVERNED_TABLES frozenset declaration."""
    table_reg = ROOT / "backend" / "app" / "store" / "table_registry.py"
    text = table_reg.read_text()
    # Match the type-annotated frozenset: GOVERNED_TABLES: frozenset[str] = frozenset({...})
    match = re.search(
        r"GOVERNED_TABLES.*?frozenset\(\{(.*?)\}\)", text, re.DOTALL
    )
    if not match:
        return -1
    # Count quoted table names
    return len(re.findall(r'"([^"]+)"', match.group(1)))


def count_projector_files() -> int:
    """Count projector_*.py files under kernel/."""
    kernel_dir = ROOT / "backend" / "app" / "core" / "runtime" / "kernel"
    return len(list(kernel_dir.glob("projectors_*.py")))


def count_god_object_max_loc() -> int:
    """Return the max LOC of known God Object candidates.

    Measures Kernel (core + query/sovereignty mixins), Brain (core + mixin), and
    MCPHub. Returns the LOC of the largest one.
    """
    kernel_dir = ROOT / "backend" / "app" / "core" / "runtime" / "kernel"

    def _loc(*paths: Path) -> int:
        total = 0
        for p in paths:
            if p.exists():
                total += len(p.read_text().splitlines())
        return total

    kernel_loc = _loc(
        kernel_dir / "kernel.py",
        kernel_dir / "kernel_query_state.py",
        kernel_dir / "kernel_sovereignty.py",
    )
    brain_loc = _loc(
        ROOT / "backend" / "app" / "core" / "agents" / "brain.py",
        ROOT / "backend" / "app" / "core" / "agents" / "brain_llm_client.py",
    )
    hub_loc = _loc(
        ROOT / "backend" / "app" / "core" / "harness" / "mcp_hub.py",
    )
    return max(kernel_loc, brain_loc, hub_loc)


# Known dead-code files that exist ONLY because of unfinished migrations or
# historical evolution.  These files have zero runtime callers.
# When a file from this list is deleted, also remove its entry here so the
# dead_code_files count decreases.
_KNOWN_DEAD_FILES: list[str] = []


def count_dead_code_files() -> int:
    """Count how many of the known dead files still exist on disk."""
    return sum(1 for p in _KNOWN_DEAD_FILES if (ROOT / p).exists())


# ── Baseline (sourced from runtime-algebra.md §4.6; updated 2026-07-04) ─────

# When you *reduce* a metric through refactoring, update these baselines AND
# the table in docs/02-concepts/runtime-algebra.md §4.6.

BASELINE = {
    "runtime_files": 44,               # concept compression merges (capability_context removed)
    "event_types": 50,                # event type compression                 # unchanged
    "query_state_selectors": 10,       # dropped goals/timer/background/user_profile
    "fragments": 10,                   # register.py
    "governed_tables": 14,             # unchanged
    "projector_files": 6,              # telemetry folded into projectors_governance
    "god_object_max_loc": 559,        # after governance fold into kernel.py
    "dead_code_files": 0,              # 已知死代码文件数
}


def measure_all() -> dict[str, int]:
    return {
        "runtime_files": count_runtime_files(),
        "event_types": count_event_types(),
        "query_state_selectors": count_query_state_selectors(),
        "fragments": count_fragments(),
        "governed_tables": count_governed_tables(),
        "projector_files": count_projector_files(),
        "god_object_max_loc": count_god_object_max_loc(),
        "dead_code_files": count_dead_code_files(),
    }


def check(verbose: bool = True, strict: bool = False) -> int:
    """Return 0 when safe, 1 when any metric exceeds baseline without
    a corresponding reduction elsewhere.

    In strict mode, dead_code_files must be 0 (i.e. all known dead files
    deleted).  Non-strict (default) only requires no *new* dead files.
    """
    current = measure_all()
    violations = 0

    for key, baseline_val in BASELINE.items():
        cur = current[key]
        limit = baseline_val

        # In strict mode, dead_code_files must reach 0.
        if strict and key == "dead_code_files":
            limit = 0

        if cur > limit:
            violations += 1
            if verbose:
                direction = ">" if cur > baseline_val else ">"
                print(
                    f"  ❌ {key}: {cur} > {limit} "
                    f"(+{cur - limit})"
                )
        elif verbose:
            status = "  ✅"
            print(f"  {status} {key}: {cur} (≤ {limit})")

    if verbose:
        print()
        if violations:
            print(
                f"FAIL: {violations} metric(s) exceed baseline.\n"
                "If this increase is intentional (e.g. a new concept), the PR must\n"
                "also DELETE an existing concept so the net change is ≤ 0.\n"
                "See docs/02-concepts/runtime-algebra.md §3.2 (Concept Addition Cost)."
            )
        else:
            print("PASS: all metrics within baseline.")

    return 1 if violations > 0 else 0


def _record_snapshot():
    """Append current metrics to the architecture history file (JSONL).

    Used by CI and `make architecture-record` to build the trend timeline
    consumed by `health_dashboard.py`.
    """
    import json
    from datetime import UTC, datetime

    current: dict[str, int | str] = dict(measure_all())
    current["ts"] = datetime.now(UTC).isoformat()

    data_dir = ROOT / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    history = data_dir / "architecture_history.jsonl"

    with open(history, "a") as f:
        f.write(json.dumps(current) + "\n")

    print(f"Snapshot recorded ({len(list(open(history)))} total): {current['ts']}")
    # Also run check so the record step gates on the same baseline
    code = check(verbose=False)
    if code != 0:
        print("WARNING: current metrics exceed baseline — snapshot recorded but check would fail.")


def snapshot():
    """Print current measurements as a markdown table for the baseline doc."""
    current = measure_all()
    print("Current Architecture Contract baseline:")
    print()
    print("| 指标 | 当前值 | 1 年目标 |")
    print("|---|---|---|")
    print(f"| `core/runtime/` 文件数 | {current['runtime_files']} | ≤ {max(current['runtime_files'] - 16, 45)} |")
    print(f"| `constants.py` 事件类型数 | {current['event_types']} | ≤ {max(current['event_types'] - 12, 55)} |")
    print(f"| `query_state` selector 分支数 | {current['query_state_selectors']} | ≤ {max(current['query_state_selectors'] - 5, 10)} |")
    print(f"| Fragment 注册数 | {current['fragments']} | ≤ {max(current['fragments'] - 3, 10)} |")
    print(f"| Governed 表数 | {current['governed_tables']} | ≤ {max(current['governed_tables'] - 2, 13)} |")
    print(f"| Projector 文件数 | {current['projector_files']} | ≤ {max(current['projector_files'] - 3, 7)} |")
    print(f"| God Object 最大 LOC | {current['god_object_max_loc']} | ≤ {max(current['god_object_max_loc'] - 500, 1500)} |")
    print(f"| Dead Code 文件数 | {current['dead_code_files']} | 0 |")


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    elif "--record" in sys.argv:
        _record_snapshot()
    else:
        strict = "--strict" in sys.argv
        sys.exit(check(strict=strict))

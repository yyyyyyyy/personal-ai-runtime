"""Concept Growth Baseline Check — enforces the Runtime Algebra evolution contract.

Reads the current concept baseline from ``runtime-algebra.md`` §4.6 and
fails if any tracked metric has grown since the last recorded baseline.

This script is intended as a CI gate (see ``make concept-growth``).
When you intentionally reduce a metric, update the baseline table in the
algebra doc to match.

Usage:
    python scripts/check_concept_growth.py          # check against baseline
    python scripts/check_concept_growth.py --snapshot  # print current values
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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


# ── Baseline (sourced from runtime-algebra.md §4.6) ─────────────────────────

# These are the current values as of 2026-07-03.
# When you *reduce* a metric through refactoring, update these baselines AND
# the table in docs/02-concepts/runtime-algebra.md §4.6.

BASELINE = {
    "runtime_files": 61,      # core/runtime/ 递归 .py 文件数
    "event_types": 69,        # constants.py 中的 EVENT_* = "..." 赋值 (+4 WorkItem)
    "query_state_selectors": 15,  # +1 work_items selector
    "fragments": 13,          # register.py 的 _ALL_FRAGMENT_CLASSES 中的 Fragment 类
    "governed_tables": 15,    # +1 work_items table
    "projector_files": 10,    # kernel/projectors_*.py 文件数
}


def measure_all() -> dict[str, int]:
    return {
        "runtime_files": count_runtime_files(),
        "event_types": count_event_types(),
        "query_state_selectors": count_query_state_selectors(),
        "fragments": count_fragments(),
        "governed_tables": count_governed_tables(),
        "projector_files": count_projector_files(),
    }


def check(verbose: bool = True) -> int:
    """Return 0 when safe, 1 when any metric exceeds baseline without
    a corresponding reduction elsewhere."""
    current = measure_all()
    violations = 0

    for key, baseline_val in BASELINE.items():
        cur = current[key]
        if cur > baseline_val:
            violations += 1
            if verbose:
                print(
                    f"  ❌ {key}: {cur} > baseline {baseline_val} "
                    f"(+{cur - baseline_val})"
                )
        elif verbose:
            status = "  ✅" if cur <= baseline_val else "  ⚠️"
            print(f"  {status} {key}: {cur} (baseline ≤ {baseline_val})")

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


def snapshot():
    """Print current measurements as a JSON-like block for the baseline table."""
    current = measure_all()
    print("Current concept baseline:")
    print()
    print("| 指标 | 当前值 | 目标值 (1 年后) |")
    print("|---|---|---|")
    print(f"| `core/runtime/` 文件数 | {current['runtime_files']} | ≤ {current['runtime_files'] - 5} |")
    print(f"| `constants.py` 事件类型数 | {current['event_types']} | ≤ {current['event_types'] - 10} |")
    print(f"| `query_state` selector 分支数 | {current['query_state_selectors']} | ≤ {max(current['query_state_selectors'] - 6, 5)} |")
    print(f"| Fragment 注册数 | {current['fragments']} | ≤ {max(current['fragments'] - 2, 8)} |")
    print(f"| Governed 表数 | {current['governed_tables']} | ≤ {max(current['governed_tables'] - 5, 10)} |")
    print(f"| Projector 文件数 | {current['projector_files']} | ≤ {max(current['projector_files'] - 3, 5)} |")


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    else:
        sys.exit(check())

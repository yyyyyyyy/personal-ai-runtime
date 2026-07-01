#!/usr/bin/env python
"""Kernel boundary guard — governed projection + execution authority.

Scans Python files under app/ (User Space) and fails if code bypasses Kernel:
  - INSERT/UPDATE/DELETE on governed projection tables
  - SELECT from governed projection tables
  - imports app.core.harness.mcp_hub (except Kernel + harness)

Known historical violations are allowlisted so CI blocks *new* bypasses only.
Shrink the allowlist as violations are fixed (target: empty).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TextIO

PROJECTION_TABLES = (
    "goals",
    "actions",
    "approvals",
    "tasks",
    "memories",
    "messages",
    "conversations",
    "notifications",
    "event_log",
    "timer_events",
    "policy_events",
    "grant_events",
    # C1: ban INSERT INTO the legacy events table (single source of truth = event_log)
    "events",
)
KERNEL_PREFIX = Path("core/runtime/kernel")
HARNESS_PREFIX = Path("core/harness")

DML_WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(" + "|".join(PROJECTION_TABLES) + r")\b",
    re.IGNORECASE,
)
SELECT_PATTERN = re.compile(
    r"\bSELECT\b[\s\S]{0,200}?\bFROM\s+(" + "|".join(PROJECTION_TABLES) + r")\b",
    re.IGNORECASE,
)
MCP_HUB_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+app\.core\.harness\.mcp_hub\s+import|import\s+app\.core\.harness\.mcp_hub)\b",
    re.MULTILINE,
)

# Violation key: (posix path under app/, line number, kind, target table/module)
ViolationKey = tuple[str, int, str, str]

# Known debt — remove entries as files migrate to kernel.query_state / kernel.read_events.
# Target: empty set (Boundary Debt = 0).
KNOWN_VIOLATION_ALLOWLIST: frozenset[ViolationKey] = frozenset()


def _is_kernel_space(rel: Path) -> bool:
    return rel.parts[: len(KERNEL_PREFIX.parts)] == KERNEL_PREFIX.parts


def _is_harness(rel: Path) -> bool:
    return rel.parts[: len(HARNESS_PREFIX.parts)] == HARNESS_PREFIX.parts


def _capability_subsystem_file(rel: Path) -> bool:
    """Files allowed to import mcp_hub."""
    if _is_kernel_space(rel) or _is_harness(rel):
        return True
    return rel in {
        Path("core/runtime/capability_policy.py"),
        Path("core/runtime/sensitive_router.py"),
        Path("core/runtime/capability_decision.py"),  # ADR-0007 Step 9: CapabilityGateway (deprecated v0.4.0)
        Path("core/runtime/capability_governance.py"),  # v0.4.0: merged governance
        Path("core/runtime/runtime_container.py"),  # v0.5.0: DI container for all subsystems
        Path("core/runtime/read_ports.py"),  # Fragment-facing read abstractions
    }


def _is_store_layer(rel: Path) -> bool:
    """database.py is the projection read layer (SELECT-only for governed tables)."""
    return rel == Path("store/database.py")


def _is_app_storage_file(rel: Path) -> bool:
    """Files that directly access APP_STORAGE tables (allowed by P8).

    APP_STORAGE tables (background_tasks, inbox_emails, etc.) may be read
    directly by worker/operational code. The boundary guard scans for access to
    GOVERNED tables only, so these files must be excluded from the DML scan.
    """
    return rel in {
        Path("core/runtime/background_worker.py"),
    }


def _in_scan_scope(rel: Path) -> bool:
    """User Space: all app/ code except Kernel Space, store layer, and app-storage workers."""
    return not _is_kernel_space(rel) and not _is_store_layer(rel) and not _is_app_storage_file(rel)


def scan_app_root(app_root: Path) -> list[tuple[Path, int, str, str, str]]:
    """Return violations as (path, line_no, line, target, kind)."""
    violations: list[tuple[Path, int, str, str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        rel = path.relative_to(app_root)
        if not _in_scan_scope(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        if not _capability_subsystem_file(rel) and MCP_HUB_IMPORT_PATTERN.search(text):
            for match in MCP_HUB_IMPORT_PATTERN.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                line = text.splitlines()[line_no - 1].strip()
                violations.append((rel, line_no, line, "mcp_hub", "import"))

        for lineno, line in enumerate(text.splitlines(), start=1):
            write_match = DML_WRITE_PATTERN.search(line)
            if write_match:
                violations.append(
                    (rel, lineno, line.strip(), write_match.group(2).lower(), "dml_write")
                )
                continue
            select_match = SELECT_PATTERN.search(line)
            if select_match:
                violations.append(
                    (rel, lineno, line.strip(), select_match.group(1).lower(), "select")
                )
    return violations


def violation_key(rel: Path, lineno: int, target: str, kind: str) -> ViolationKey:
    return (rel.as_posix(), lineno, kind, target)


def partition_violations(
    violations: list[tuple[Path, int, str, str, str]],
    allowlist: frozenset[ViolationKey],
) -> tuple[list[tuple[Path, int, str, str, str]], list[tuple[Path, int, str, str, str]]]:
    known: list[tuple[Path, int, str, str, str]] = []
    new: list[tuple[Path, int, str, str, str]] = []
    for item in violations:
        rel, lineno, _line, target, kind = item
        key = violation_key(rel, lineno, target, kind)
        if key in allowlist:
            known.append(item)
        else:
            new.append(item)
    return known, new


def print_violations(
    violations: list[tuple[Path, int, str, str, str]],
    *,
    header: str,
    stream: TextIO = sys.stderr,
) -> None:
    print(header, file=stream)
    for rel, lineno, line, target, kind in violations:
        print(f"  {rel.as_posix()}:{lineno} [{kind}:{target}] {line}", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kernel boundary guard for Personal AI Runtime")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print all violations (known + new) and exit 0",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on allowlisted violations too (use when allowlist is empty)",
    )
    args = parser.parse_args(argv)

    backend = Path(__file__).resolve().parent.parent
    app_root = backend / "app"
    if not app_root.is_dir():
        print(f"ERROR: app root not found: {app_root}", file=sys.stderr)
        return 1

    violations = scan_app_root(app_root)
    known, new = partition_violations(violations, KNOWN_VIOLATION_ALLOWLIST)

    if args.inventory:
        print("KERNEL BOUNDARY INVENTORY")
        print(f"  Scan scope: app/ except {KERNEL_PREFIX.as_posix()}/")
        print(f"  Total violations: {len(violations)}")
        print(f"  Known (allowlisted): {len(known)}")
        print(f"  New (would fail CI): {len(new)}")
        if known:
            print_violations(known, header="\nKnown violations (allowlisted debt):", stream=sys.stdout)
        if new:
            print_violations(new, header="\nNew violations:", stream=sys.stdout)
        if not violations:
            print("\nNo governed bypass detected.")
        return 0

    if new:
        print_violations(
            new,
            header="KERNEL BOUNDARY VIOLATION — new governed/execution bypass (not in allowlist):",
        )
        if known:
            print(
                f"\n({len(known)} known allowlisted violation(s) — run --inventory to list)",
                file=sys.stderr,
            )
        return 1

    if args.strict and known:
        print_violations(
            known,
            header="KERNEL BOUNDARY VIOLATION — allowlisted debt (--strict mode):",
        )
        return 1

    if known:
        print(
            f"KERNEL BOUNDARY OK — no new bypasses "
            f"({len(known)} known allowlisted violation(s), run --inventory)"
        )
    else:
        print("KERNEL BOUNDARY OK — no governed/execution bypass outside kernel/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Kernel boundary guard — governed projection + execution authority.

Scans Python files under app/ and fails if User Space:
  - INSERT/UPDATE/DELETE on governed projection tables
  - SELECT from governed projection tables
  - imports app.core.harness.mcp_hub (except Kernel + capability subsystem)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECTION_TABLES = ("goals", "actions", "approvals", "tasks", "memories", "event_log")
KERNEL_PREFIX = Path("core/runtime/kernel")
CAPABILITY_SUBSYSTEM_PREFIXES = (
    Path("core/runtime/kernel"),
    Path("core/harness"),
    Path("core/runtime/capability_policy.py"),
    Path("core/runtime/sensitive_router.py"),
)
USER_SPACE_PREFIXES = (
    Path("api"),
    Path("core/agents"),
    Path("core/runtime"),
)

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


def _in_user_space(rel: Path) -> bool:
    if rel.parts[: len(KERNEL_PREFIX.parts)] == KERNEL_PREFIX.parts:
        return False
    return any(rel.parts[: len(p.parts)] == p.parts for p in USER_SPACE_PREFIXES)


def _capability_subsystem_file(rel: Path) -> bool:
    if rel.parts[: len(Path("core/harness").parts)] == Path("core/harness").parts:
        return True
    if rel.parts[: len(KERNEL_PREFIX.parts)] == KERNEL_PREFIX.parts:
        return True
    return rel in {
        Path("core/runtime/capability_policy.py"),
        Path("core/runtime/sensitive_router.py"),
    }


def scan_app_root(app_root: Path) -> list[tuple[Path, int, str, str, str]]:
    """Return violations as (path, line_no, line, target, kind)."""
    violations: list[tuple[Path, int, str, str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        rel = path.relative_to(app_root)
        if not _in_user_space(rel):
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


def main() -> int:
    backend = Path(__file__).resolve().parent.parent
    app_root = backend / "app"
    if not app_root.is_dir():
        print(f"ERROR: app root not found: {app_root}", file=sys.stderr)
        return 1

    violations = scan_app_root(app_root)
    if violations:
        print("KERNEL BOUNDARY VIOLATION — User Space governed/execution bypass:", file=sys.stderr)
        for rel, lineno, line, target, kind in violations:
            print(f"  {rel}:{lineno} [{kind}:{target}] {line}", file=sys.stderr)
        return 1

    print("KERNEL BOUNDARY OK — no governed/execution bypass outside kernel/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Kernel boundary guard — projection tables may only be written from Kernel Space.

Scans all Python files under app/ and fails if INSERT/UPDATE/DELETE targets
goals, approvals, tasks, memories, or event_log outside app/core/runtime/kernel/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECTION_TABLES = ("goals", "approvals", "tasks", "memories", "event_log")
# Paths are relative to backend/app (the scan root).
ALLOWED_PREFIX = Path("core/runtime/kernel")

# Match SQL DML against projection tables (string literals in execute() calls).
DML_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(" + "|".join(PROJECTION_TABLES) + r")\b",
    re.IGNORECASE,
)


def scan_app_root(app_root: Path) -> list[tuple[Path, int, str, str]]:
    """Return violations as (path, line_no, line, table)."""
    violations: list[tuple[Path, int, str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        rel = path.relative_to(app_root)
        if rel.parts[: len(ALLOWED_PREFIX.parts)] == ALLOWED_PREFIX.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = DML_PATTERN.search(line)
            if match:
                violations.append((rel, lineno, line.strip(), match.group(2).lower()))
    return violations


def main() -> int:
    backend = Path(__file__).resolve().parent.parent
    app_root = backend / "app"
    if not app_root.is_dir():
        print(f"ERROR: app root not found: {app_root}", file=sys.stderr)
        return 1

    violations = scan_app_root(app_root)
    if violations:
        print("KERNEL BOUNDARY VIOLATION — direct projection writes in User Space:", file=sys.stderr)
        for rel, lineno, line, table in violations:
            print(f"  {rel}:{lineno} [{table}] {line}", file=sys.stderr)
        return 1

    print("KERNEL BOUNDARY OK — no direct projection writes outside kernel/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Execution Ownership guard — verify invoke_capability carries execution_id.

Scans Python files under app/ (User Space) for kernel.invoke_capability calls.
Fails if a call does NOT pass execution_id and the file is not in the known
bypass allowlist.

Philosophy (same as check_boundary.py):
    Runtime's biggest progress is not "define rules" but "make rules CI-enforced".
    Execution Ownership cannot stay an ADR — it MUST be machine-verified.

Bypass allowlist tracks known debt. Shrink it as each bypass path is closed.
Target: empty allowlist = Execution Ownership fully enforced.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TextIO

KERNEL_PREFIX = Path("core/runtime/kernel")
CALL_PATTERN = re.compile(
    r"kernel\.invoke_capability\s*\(|\.invoke_capability\s*\(",
)

# All invoke_capability call sites pass execution_id.
# Target: empty allowlist = Execution Ownership fully enforced.
BYPASS_ALLOWLIST: frozenset[tuple[str, int, str]] = frozenset()


def _is_kernel_space(rel: Path) -> bool:
    return rel.parts[:len(KERNEL_PREFIX.parts)] == KERNEL_PREFIX.parts


def _find_matching_paren(text: str, start: int) -> int:
    """Find the closing ) that matches the opening ( at start.

    Handles nested parentheses and string literals.
    """
    depth = 0
    in_string = False
    string_char = ""
    i = start

    while i < len(text):
        ch = text[i]

        # Track string boundaries to avoid matching parens inside strings
        if not in_string and ch in ('"', "'"):
            in_string = True
            string_char = ch
        elif in_string:
            if ch == "\\":
                i += 1  # skip escaped char
            elif ch == string_char:
                in_string = False
                string_char = ""
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i

        i += 1

    return -1


def _check_call_passes_execution_id(call_text: str) -> bool:
    """Check if the invoke_capability call passes execution_id."""
    return "execution_id" in call_text


def scan_app_root(
    app_root: Path,
    allowlist: frozenset[tuple[str, int, str]],
) -> tuple[list[tuple[Path, int, str]], list[tuple[Path, int, str, str]]]:
    """Scan User Space for invoke_capability calls without execution_id.

    Returns (known_bypasses, new_violations).
    known_bypasses: (path, line, reason) — in allowlist
    new_violations: (path, line, snippet, hint) — NOT in allowlist
    """
    known: list[tuple[Path, int, str]] = []
    new: list[tuple[Path, int, str, str]] = []

    for path in sorted(app_root.rglob("*.py")):
        rel = path.relative_to(app_root)
        if _is_kernel_space(rel):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        for match in CALL_PATTERN.finditer(text):
            # Find the opening paren
            open_paren = text.find("(", match.end() - 1)
            if open_paren == -1:
                continue

            close_paren = _find_matching_paren(text, open_paren)
            if close_paren == -1:
                continue

            call_text = text[open_paren:close_paren + 1]
            if _check_call_passes_execution_id(call_text):
                continue

            # Determine line number
            line_no = text.count("\n", 0, open_paren) + 1  # 1-indexed

            # Check allowlist
            rel_posix = rel.as_posix()
            is_allowed = False
            allowed_reason = ""
            for al_rel, al_line, al_reason in allowlist:
                if al_rel == rel_posix and (al_line == 0 or al_line == line_no):
                    is_allowed = True
                    allowed_reason = al_reason
                    break

            if is_allowed:
                known.append((rel, line_no, allowed_reason))
            else:
                snippet = text.splitlines()[line_no - 1].strip()
                new.append((rel, line_no, snippet, "missing execution_id"))

    return known, new


def print_known(known: list[tuple[Path, int, str]], stream: TextIO) -> None:
    if not known:
        return
    print("\nKnown bypasses (allowlisted):", file=stream)
    for rel, line, reason in known:
        print(f"  {rel.as_posix()}:{line}  [{reason}]", file=stream)


def print_violations(
    violations: list[tuple[Path, int, str, str]],
    header: str,
    stream: TextIO = sys.stderr,
) -> None:
    if not violations:
        return
    print(header, file=stream)
    for rel, line, snippet, hint in violations:
        print(f"  {rel.as_posix()}:{line}  [{hint}]  {snippet}", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execution Ownership guard for Personal AI Runtime",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print all bypasses (known + new) and exit 0",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on allowlisted bypasses too (target: empty allowlist)",
    )
    args = parser.parse_args(argv)

    backend = Path(__file__).resolve().parent.parent
    app_root = backend / "app"
    if not app_root.is_dir():
        print(f"ERROR: app root not found: {app_root}", file=sys.stderr)
        return 1

    known, new = scan_app_root(app_root, BYPASS_ALLOWLIST)

    if args.inventory:
        print("EXECUTION OWNERSHIP INVENTORY")
        print(f"  Scan scope: app/ except {KERNEL_PREFIX.as_posix()}/")
        total = len(known) + len(new)
        print(f"  Total bypasses: {total}")
        print(f"  Known (allowlisted): {len(known)}")
        print(f"  New (would fail CI): {len(new)}")
        print_known(known, sys.stdout)
        if new:
            print_violations(
                new,
                "\nNEW BYPASS — invoke_capability without execution_id:",
                sys.stdout,
            )
        if not total:
            print("\nExecution Ownership fully enforced — every invoke_capability "
                  "carries execution_id.")
        return 0

    if new:
        print_violations(
            new,
            "EXECUTION OWNERSHIP VIOLATION — invoke_capability without execution_id "
            "(not in allowlist):",
        )
        if known:
            print(
                f"\n({len(known)} known allowlisted bypass(es) — run --inventory)",
                file=sys.stderr,
            )
        return 1

    if args.strict and known:
        print_violations(
            [(r, ln, "", reason) for r, ln, reason in known],
            "EXECUTION OWNERSHIP — allowlisted debt (--strict mode):",
        )
        return 1

    if known:
        print(
            f"EXECUTION OWNERSHIP OK — no new bypasses "
            f"({len(known)} known allowlisted bypass(es), run --inventory)"
        )
    else:
        print("EXECUTION OWNERSHIP OK — every invoke_capability in User Space "
              "carries execution_id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

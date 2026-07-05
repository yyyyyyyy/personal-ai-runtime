#!/usr/bin/env python
"""Verify docs contain no ``.py:NNN`` line-number references.

Line numbers in doc links drift every refactor (function moves, file grows,
lines renumber). The repo switched to function-name references in v0.9.0
for stability. This guard blocks new line-number references from creeping
back into docs.

Exit codes:
  0 — no line-number refs found
  1 — drift detected
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_DOCS = _ROOT / "docs"

# Match a markdown link whose label is a backtick-quoted path ending in
# .py:NNN or .py:NNN-NNN. Examples that fail:
#   [`kernel.py:42`](path)
#   [`backend/app/foo.py:108-188`](path)
# Also catches line refs in inline code outside links:
#   see `kernel.py:42-94` for details
LINK_PATTERN = re.compile(r"\[`[^`]+?\.py:\d+(?:-\d+)?`\]")
INLINE_PATTERN = re.compile(r"`[^`]+?\.py:\d+(?:-\d+)?`")


def main() -> int:
    if not _DOCS.is_dir():
        print(f"ERROR: {_DOCS} not found", file=sys.stderr)
        return 2

    violations: list[str] = []

    for md_file in sorted(_DOCS.rglob("*.md")):
        rel = md_file.relative_to(_ROOT)
        for lineno, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
            for pat in (LINK_PATTERN, INLINE_PATTERN):
                for m in pat.finditer(line):
                    violations.append(f"{rel}:{lineno}: {m.group(0)}")

    if violations:
        print("DOC LINE-REF GUARD FAILED — line-number refs drift on refactor", file=sys.stderr)
        print(
            "Use function-name references instead: [`foo.py`](path) of `ClassName.method`",
            file=sys.stderr,
        )
        print()
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("DOC LINE-REF GUARD OK — no line-number references in docs/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

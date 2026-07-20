#!/usr/bin/env python
"""Verify docs/04-data/data-model.md table list matches table_registry.py.

Catches the most common doc-code drift: docs claiming tables that no longer
exist (or omitting tables that do). Run in CI to prevent the data-model doc
from rotting after schema changes.

Exit codes:
  0 — docs and registry are in sync
  1 — drift detected
"""
from __future__ import annotations

from pathlib import Path

import re
import sys

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from scripts._bootstrap import BACKEND_ROOT, prepare_script_env

prepare_script_env()

_ROOT = BACKEND_ROOT.parent
_BACKEND = BACKEND_ROOT


def registry_tables() -> tuple[set[str], set[str]]:
    """Return (governed, app_storage) table name sets from table_registry.py."""
    from app.store.table_registry import APP_STORAGE_TABLES, GOVERNED_TABLES

    return set(GOVERNED_TABLES), set(APP_STORAGE_TABLES)


def doc_tables() -> set[str]:
    """Return the set of table names mentioned as schema sections in data-model.md.

    Matches:
      1. Markdown section headers of the form ``### `table_name``` or
         combined headers like ``### `conversations` / `messages```.
      2. Table names appearing in the APP_STORAGE chapter table rows
         ``| `table_name` | ... |`` (between the APP_STORAGE header and the
         next ## section, to avoid catching ChromaDB collections or Alembic
         revision ids).
    """
    doc_path = _ROOT / "docs" / "04-data" / "data-model.md"
    text = doc_path.read_text(encoding="utf-8")

    candidates: set[str] = set()

    # 1. Section headers — including combined ones like
    #    "### `conversations` / `messages`" — capture every backtick-quoted
    #    identifier on a line starting with ### .
    for line in re.finditer(r"^###\s+(.+)$", text, re.MULTILINE):
        for m in re.finditer(r"`([a-z][a-z0-9_]+)`", line.group(1)):
            candidates.add(m.group(1))

    # 2. APP_STORAGE table rows only — slice the text between the
    #    "## APP_STORAGE" header and the next "## " level-2 header so we
    #    don't pick up ChromaDB collections or Alembic revision ids from
    #    neighbouring chapters.
    storage_match = re.search(
        r"^## APP_STORAGE.*?\n(.*?)(?=^## )",
        text,
        re.MULTILINE | re.DOTALL,
    )
    storage_text = storage_match.group(1) if storage_match else ""
    for m in re.finditer(r"^\|\s*`([a-z][a-z0-9_]+)`\s*\|", storage_text, re.MULTILINE):
        candidates.add(m.group(1))

    return candidates


def main() -> int:
    governed, app_storage = registry_tables()
    registry_all = governed | app_storage

    docs = doc_tables()

    violations: list[str] = []

    # Tables in registry but missing from docs (drift: schema grew, doc didn't).
    # projection_checkpoints is an internal table; doc omission is acceptable.
    missing_from_docs = (registry_all - docs) - {"projection_checkpoints"}
    if missing_from_docs:
        violations.append(
            f"tables in registry but not in data-model.md: {sorted(missing_from_docs)}"
        )

    # Tables in docs (section headers / table rows) but not in registry
    # (drift: doc references a table that no longer exists).
    doc_extra = docs - registry_all
    if doc_extra:
        violations.append(
            f"tables mentioned in data-model.md but not in registry: {sorted(doc_extra)}"
        )

    if violations:
        print("DOC TABLE SYNC FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nUpdate docs/04-data/data-model.md or backend/app/store/table_registry.py",
            file=sys.stderr,
        )
        return 1

    print(
        f"DOC TABLE SYNC OK — {len(governed)} governed + "
        f"{len(app_storage)} app_storage tables aligned with docs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Doc link guard — fails CI when markdown references point to missing files.

Scans every ``.md`` file under ``docs/`` and the repo root (``README.md``,
``CHANGELOG.md``) for two kinds of file references and asserts each resolves
to an existing file on disk:

1. **Markdown links** — ``[label](relative/path.py)``. Only relative paths
   that look like in-repo files (no scheme, no anchor-only links) are checked.
2. **Backtick paths** — `` `path/to/file.py` ``. Only paths with a known
   source extension that exist relative to the *referencing file's parent
   dir two levels up* (docs files live in ``docs/NN-foo/`` and use
   ``../../backend/...`` style relative paths) are checked. Bare words like
   ``kernel.py`` without a directory separator are skipped to avoid
   false positives on prose.

Exit code 0 = all references resolve; 1 = broken references found.

Usage::

    python3 scripts/check_doc_links.py            # scan
    python3 scripts/check_doc_links.py --quiet    # only print failures
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Root of the repo: scripts/ lives under backend/, repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Extensions that, when seen inside backticks, indicate a file reference worth
# checking. Keeps prose backticks like `event_log` (a table) from being treated
# as a file path.
SOURCE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".toml",
    ".yml", ".yaml", ".sh", ".sql", ".ini", ".cfg", ".env", ".example",
})

# Anchor-only links, mailto, http(s), and pure-fragment refs are not file checks.
_NON_FILE_LINK = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|mailto:|#|tel:)", re.IGNORECASE)

# [label](path)  — capture path (strip optional #anchor and ?query)
_MD_LINK_RE = re.compile(r"\[(?:[^\]\\]|\\.)*\]\(([^)]+)\)")
# `path/with/slash.ext` — only paths containing a slash and a source extension.
_BACKTICK_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`")


def _clean_link_target(raw: str) -> str | None:
    """Return the path portion of a markdown link target, or None to skip."""
    target = raw.strip()
    # Drop title: [text](path "title")
    if target.endswith('"') and ' "' in target:
        target = target.rsplit(' "', 1)[0]
    # Drop anchor / query
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    if _NON_FILE_LINK.match(target):
        return None
    return target


def _looks_like_file_ref(p: str) -> bool:
    """Heuristic: backtick token is a file ref if it has a slash and a source ext."""
    if "/" not in p:
        return False
    suffix = Path(p).suffix.lower()
    return suffix in SOURCE_EXTENSIONS


def _doc_files() -> list[Path]:
    """All markdown files to scan: docs/ + repo-root *.md."""
    files: list[Path] = []
    docs = REPO_ROOT / "docs"
    if docs.is_dir():
        files.extend(sorted(docs.rglob("*.md")))
    for top in ("README.md", "CHANGELOG.md"):
        p = REPO_ROOT / top
        if p.is_file():
            files.append(p)
    return files


def _resolve_link(target: str, md_parent: Path) -> Path:
    """Resolve a markdown link target relative to the doc file's directory."""
    return (md_parent / target).resolve()


def _resolve_backtick(tok: str) -> Path | None:
    """Resolve a backtick path token against several known bases.

    Docs use abbreviated paths (e.g. ``kernel/constants.py`` for
    ``backend/app/core/runtime/kernel/constants.py``, or ``scripts/verify_*.py``
    for ``backend/scripts/verify_*.py``). Try repo-relative first, then a set
    of alias bases derived from where source actually lives across all three
    subsystems (backend, frontend, .github).
    """
    # Skip URL-like tokens and parameterised placeholders.
    if tok.startswith("/") or tok.startswith("BASE_DIR") or "$" in tok:
        return None
    bases = [
        REPO_ROOT,
        REPO_ROOT / "backend",
        REPO_ROOT / "backend" / "app" / "core" / "runtime",
        REPO_ROOT / "backend" / "app" / "core" / "runtime" / "kernel",
        REPO_ROOT / "backend" / "app" / "core" / "runtime" / "governance",
        REPO_ROOT / "backend" / "app" / "core" / "agents",
        REPO_ROOT / "backend" / "app" / "core" / "harness",
        REPO_ROOT / "backend" / "app" / "core",
        REPO_ROOT / "backend" / "app",
        REPO_ROOT / "backend" / "scripts",
        REPO_ROOT / "frontend" / "src",
        REPO_ROOT / "frontend",
        REPO_ROOT / "desktop",
        REPO_ROOT / ".github",
    ]
    for base in bases:
        candidate = (base / tok).resolve()
        try:
            candidate.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate  # found under an alias base
    # Not found under any base — return a best-guess path for the report.
    return (REPO_ROOT / tok).resolve()


def check_file(md_path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, reference, reason) for broken refs in md_path."""
    broken: list[tuple[int, str, str]] = []
    text = md_path.read_text(encoding="utf-8")

    for lineno, line in enumerate(text.splitlines(), start=1):
        # --- markdown links (resolved relative to the doc file) ---
        for m in _MD_LINK_RE.finditer(line):
            raw = m.group(1)
            target = _clean_link_target(raw)
            if target is None:
                continue
            # Skip Mermaid/node labels that get captured (e.g. "1. INSERT ...").
            if any(c in target for c in (" ", "\n", "<", ">", "{", "}")):
                continue
            resolved = _resolve_link(target, md_path.parent)
            try:
                resolved_rel = resolved.relative_to(REPO_ROOT)
            except ValueError:
                # Escaped the repo — skip (external / unusual).
                continue
            if not resolved.exists():
                broken.append((lineno, target, str(resolved_rel)))

        # --- backtick file paths (resolved relative to repo root) ---
        for m in _BACKTICK_PATH_RE.finditer(line):
            tok = m.group(1)
            if not _looks_like_file_ref(tok):
                continue
            bt_resolved = _resolve_backtick(tok)
            if bt_resolved is None:
                continue
            if not bt_resolved.exists():
                try:
                    resolved_rel = bt_resolved.relative_to(REPO_ROOT)
                    display = str(resolved_rel)
                except ValueError:
                    display = tok
                broken.append((lineno, tok, display))

    if broken:
        # De-duplicate by (lineno, reference)
        seen: set[tuple[int, str]] = set()
        unique: list[tuple[int, str, str]] = []
        for b in broken:
            key = (b[0], b[1])
            if key not in seen:
                seen.add(key)
                unique.append(b)
        broken = unique
    return broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only print broken references, not the scanning progress.",
    )
    args = parser.parse_args(argv)

    md_files = _doc_files()
    if not args.quiet:
        print(f"Scanning {len(md_files)} markdown file(s) for broken file references...")

    total_broken = 0
    for md in md_files:
        broken = check_file(md)
        if not broken:
            continue
        rel = md.relative_to(REPO_ROOT)
        total_broken += len(broken)
        for lineno, ref, _resolved in broken:
            print(f"{rel}:{lineno}: broken reference `{ref}`")

    if total_broken:
        print(f"\nFAIL: {total_broken} broken doc reference(s) found.")
        return 1

    if not args.quiet:
        print("OK: all markdown file references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

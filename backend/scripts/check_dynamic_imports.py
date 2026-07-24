#!/usr/bin/env python
"""Detect importlib / dynamic module loads that bypass AST layer/boundary guards.

Allowlisted call sites must stay minimal. New importlib.import_module /
``__import__`` usages in app/ require an explicit allowlist entry with rationale.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()

BACKEND = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND / "app"

# (posix path under app/, lineno) — shrink toward empty when possible.
IMPORTLIB_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    # BoundProxy lazy-loads runtime_container to avoid Store→Runtime hard cycle.
    ("store/bound_proxy.py", 39),
})


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_importlib_import_module(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        if isinstance(func.value, ast.Name) and func.value.id == "importlib":
            return True
        if (
            isinstance(func.value, ast.Attribute)
            and func.value.attr == "importlib"
        ):
            return True
    if isinstance(func, ast.Name) and func.id == "import_module":
        return True
    return False


def _is_dunder_import(node: ast.Call) -> bool:
    return _call_name(node.func) == "__import__"


def _is_importlib_util_loader(node: ast.Call) -> bool:
    """Catch importlib.util.module_from_spec / spec_from_file_location style loads."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {
        "module_from_spec",
        "spec_from_file_location",
        "spec_from_loader",
    }:
        return False
    # importlib.util.<attr> or util.<attr> after `from importlib import util`
    val = func.value
    if isinstance(val, ast.Attribute) and val.attr == "util":
        return True
    if isinstance(val, ast.Name) and val.id == "util":
        return True
    return False


def _is_dynamic_load(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return (
        _is_importlib_import_module(node)
        or _is_dunder_import(node)
        or _is_importlib_util_loader(node)
    )


def main() -> int:
    violations: list[str] = []
    seen_allow: set[tuple[str, int]] = set()
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(APP_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not _is_dynamic_load(node):
                continue
            key = (rel, int(getattr(node, "lineno", 0)))
            if key in IMPORTLIB_ALLOWLIST:
                seen_allow.add(key)
                continue
            path_allowed = {p for p, _ln in IMPORTLIB_ALLOWLIST}
            kind = "dynamic import"
            if isinstance(node, ast.Call):
                if _is_dunder_import(node):
                    kind = "__import__"
                elif _is_importlib_util_loader(node):
                    kind = "importlib.util loader"
                else:
                    kind = "importlib.import_module"
            if rel in path_allowed:
                violations.append(
                    f"{rel}:{key[1]}: {kind} (update "
                    f"IMPORTLIB_ALLOWLIST lineno; was allowlisted for this file)"
                )
            else:
                violations.append(
                    f"{rel}:{key[1]}: {kind} bypasses AST "
                    "layer/boundary guards — add to IMPORTLIB_ALLOWLIST with rationale"
                )

    stale = set(IMPORTLIB_ALLOWLIST) - seen_allow
    for rel, ln in list(stale):
        fpath = APP_ROOT / rel
        if not fpath.exists():
            violations.append(f"{rel}:{ln}: allowlist entry missing file")
            continue
        text = fpath.read_text(encoding="utf-8")
        if "import_module" in text or "__import__" in text:
            stale.discard((rel, ln))

    if stale:
        for rel, ln in sorted(stale):
            violations.append(
                f"{rel}:{ln}: stale IMPORTLIB_ALLOWLIST entry (no dynamic import found)"
            )

    if violations:
        print("DYNAMIC IMPORT GUARD FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(
        f"DYNAMIC IMPORT GUARD OK — {len(IMPORTLIB_ALLOWLIST)} allowlisted "
        "dynamic-import site(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

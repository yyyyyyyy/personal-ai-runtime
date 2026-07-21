#!/usr/bin/env python
"""Layer dependency guard — Runtime / Product / Store / API import edges.

Complements ``check_boundary.py`` (storage GOLDEN RULE). This script enforces
*responsibility* edges from docs/02-concepts/architecture-principles.md:

  R1  core/runtime  ─X→  app.product          (mechanism must not call domain)
  R2  store         ─X→  app.core.runtime     (storage must not assemble Runtime)
  R3  api           ─X→  private runtime names (``_foo``) and deep Runtime modules
                         outside the published ABI surface
  R4  product       may use Kernel ABI; deep Runtime modules are debt

Known crossings are allowlisted so CI blocks *new* edges only.
Shrink DEBT_ALLOWLIST as edges are removed (target: empty for R1/R2).

Limitations (same class as check_boundary): does not see ``importlib`` /
dynamic imports or relative imports (``from .foo import …``).
``core/agents`` → Product is User Space and intentionally unscanned.
``core/harness`` domain tools are a separate directory-drift debt (R1 only
covers ``core/runtime``).

Usage:
    python -m scripts.check_layer_deps
    python -m scripts.check_layer_deps --inventory
    python -m scripts.check_layer_deps --strict   # fail if any allowlisted debt remains
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()

BACKEND = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND / "app"

# ── Published API / Product ABI surface (always allowed) ─────────────────────

API_ABI_PREFIXES: tuple[str, ...] = (
    "app.core.runtime.read_ports",
    "app.core.runtime.kernel_instance",
    "app.core.runtime.kernel.constants",
    "app.core.runtime.runtime_config",
    "app.core.runtime.egress",
)

# ``from app.core.runtime import read_ports`` / ``kernel_instance`` style
# (package path ``read_ports`` = Ports ABI: reads + command/bridge wrappers).
API_ABI_PACKAGE_NAMES: frozenset[str] = frozenset({
    "read_ports",
    "kernel_instance",
})

PRODUCT_ABI_PREFIXES: tuple[str, ...] = (
    "app.core.runtime.read_ports",
    "app.core.runtime.kernel_instance",
    "app.core.runtime.kernel.constants",
    "app.core.runtime.egress",
)

# Exact module paths allowed for Product (not prefix-matched into children).
PRODUCT_ABI_EXACT: frozenset[str] = frozenset({
    "app.core.runtime.kernel",  # ``from app.core.runtime.kernel import Kernel`` only
})

PRODUCT_ABI_PACKAGE_NAMES: frozenset[str] = frozenset({
    "read_ports",
    "kernel_instance",
})

# ── Known debt (file, kind, module) — shrink toward empty for R1/R2 ───────────

DebtKey = tuple[str, str, str]

DEBT_ALLOWLIST: frozenset[DebtKey] = frozenset({
    # R1 — Runtime → Product
    ("core/runtime/notification_bridge.py", "runtime_to_product", "app.product.notifications"),
    ("core/runtime/builtin_reactions.py", "runtime_to_product", "app.product.notifications"),
    ("core/runtime/handlers/inbox_poll_handlers.py", "runtime_to_product", "app.product.inbox"),
    # R2 — Store → Runtime
    ("store/database.py", "store_to_runtime", "app.core.runtime.runtime_container"),
    ("store/vector.py", "store_to_runtime", "app.core.runtime.runtime_container"),
})


def _import_targets(node: ast.AST) -> list[tuple[str, bool]]:
    """Return (module_target, is_private) for dependency matching.

    ``from app.core.runtime.task_engine import create_work_item`` →
        ``app.core.runtime.task_engine`` (one hit for the module).
    ``from app.core.runtime import read_ports`` →
        ``app.core.runtime.read_ports`` (ABI leaf).
    ``from app.core.runtime.runtime_config import _is_masked`` →
        ``app.core.runtime.runtime_config._is_masked`` (private).
    """
    out: list[tuple[str, bool]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.append((alias.name, False))
        return out
    if not isinstance(node, ast.ImportFrom) or not node.module:
        return out
    base = node.module
    for alias in node.names:
        name = alias.name
        if name == "*":
            out.append((base, False))
            continue
        if name.startswith("_"):
            out.append((f"{base}.{name}", True))
            continue
        if base == "app.core.runtime":
            # ``from app.core.runtime import read_ports`` / unexpected leaf
            out.append((f"{base}.{name}", False))
            continue
        if base == "app.product":
            out.append((f"{base}.{name}", False))
            continue
        if base == "app.core.runtime.kernel":
            # ``import Kernel`` → exact package (type hint ABI);
            # ``import constants`` / other → submodule path (constants ABI, else debt).
            if name == "Kernel":
                out.append((base, False))
            else:
                out.append((f"{base}.{name}", False))
            continue
        out.append((base, False))
    return out


def _iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _parse_imports(path: Path) -> list[tuple[int, str, bool]]:
    """Return (lineno, module_target, is_private)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    found: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for mod, private in _import_targets(node):
                found.append((getattr(node, "lineno", 1), mod, private))
    return found


def _starts_with(mod: str, prefix: str) -> bool:
    return mod == prefix or mod.startswith(prefix + ".")


def _is_abi(
    mod: str,
    prefixes: tuple[str, ...],
    package_names: frozenset[str],
    *,
    exact: frozenset[str] | None = None,
) -> bool:
    if exact and mod in exact:
        return True
    for p in prefixes:
        if _starts_with(mod, p):
            # public runtime_config only
            if p == "app.core.runtime.runtime_config":
                rest = mod[len(p) :]
                if rest.startswith("._"):
                    return False
            return True
    # app.core.runtime.read_ports (exact leaf from package import)
    if mod.startswith("app.core.runtime."):
        leaf = mod[len("app.core.runtime.") :]
        if leaf in package_names:
            return True
    return False


def scan() -> list[tuple[str, int, str, str, str]]:
    """Return violations: (rel_posix, lineno, kind, module, hint)."""
    violations: list[tuple[str, int, str, str, str]] = []

    for path in _iter_py_files(APP_ROOT):
        rel = path.relative_to(APP_ROOT).as_posix()
        parts = Path(rel).parts

        for lineno, mod, is_private in _parse_imports(path):
            # R1: core/runtime → product
            if parts[:2] == ("core", "runtime") and (
                mod == "app.product" or mod.startswith("app.product.")
            ):
                target = ".".join(mod.split(".")[:3])  # app.product.<pkg>
                violations.append((rel, lineno, "runtime_to_product", target, mod))

            # R2: store → runtime
            if parts[:1] == ("store",) and (
                mod == "app.core.runtime" or mod.startswith("app.core.runtime.")
            ):
                target = (
                    "app.core.runtime.runtime_container"
                    if "runtime_container" in mod
                    else mod
                )
                violations.append((rel, lineno, "store_to_runtime", target, mod))

            # R3: api → runtime
            if parts[:1] == ("api",) and (
                mod == "app.core.runtime" or mod.startswith("app.core.runtime.")
            ):
                if is_private:
                    violations.append((rel, lineno, "api_private_import", mod, mod))
                elif not _is_abi(mod, API_ABI_PREFIXES, API_ABI_PACKAGE_NAMES):
                    violations.append((rel, lineno, "api_deep_runtime", mod, mod))

            # R4: product → deep runtime
            if parts[:1] == ("product",) and (
                mod == "app.core.runtime" or mod.startswith("app.core.runtime.")
            ):
                if _is_abi(
                    mod,
                    PRODUCT_ABI_PREFIXES,
                    PRODUCT_ABI_PACKAGE_NAMES,
                    exact=PRODUCT_ABI_EXACT,
                ):
                    continue
                violations.append((rel, lineno, "product_deep_runtime", mod, mod))

    return _dedupe(violations)


def _dedupe(
    items: list[tuple[str, int, str, str, str]],
) -> list[tuple[str, int, str, str, str]]:
    """One row per (file, kind, target); keep lowest lineno."""
    best: dict[tuple[str, str, str], tuple[str, int, str, str, str]] = {}
    for rel, lineno, kind, target, hint in items:
        key = (rel, kind, target)
        prev = best.get(key)
        if prev is None or lineno < prev[1]:
            best[key] = (rel, lineno, kind, target, hint)
    return sorted(best.values(), key=lambda x: (x[0], x[2], x[3], x[1]))


def debt_key(rel: str, kind: str, target: str) -> DebtKey:
    return (rel, kind, target)


def partition(
    violations: list[tuple[str, int, str, str, str]],
) -> tuple[
    list[tuple[str, int, str, str, str]],
    list[tuple[str, int, str, str, str]],
]:
    known: list[tuple[str, int, str, str, str]] = []
    new: list[tuple[str, int, str, str, str]] = []
    for item in violations:
        rel, _lineno, kind, target, _hint = item
        if debt_key(rel, kind, target) in DEBT_ALLOWLIST:
            known.append(item)
        else:
            new.append(item)
    return known, new


def stale_allowlist_entries(
    violations: list[tuple[str, int, str, str, str]],
) -> list[DebtKey]:
    present = {debt_key(r, k, t) for r, _ln, k, t, _h in violations}
    return sorted(DEBT_ALLOWLIST - present)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Layer dependency guard")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="List all crossings (known debt + new) and exit 0",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any allowlisted debt remains",
    )
    args = parser.parse_args(argv)

    violations = scan()
    known, new = partition(violations)
    stale = stale_allowlist_entries(violations)

    if args.inventory:
        print("LAYER DEPS INVENTORY")
        print(f"  Total crossings: {len(violations)}")
        print(f"  Known debt (allowlisted): {len(known)}")
        print(f"  New (would fail CI): {len(new)}")
        print(f"  Stale allowlist entries: {len(stale)}")
        print()
        for rel, lineno, kind, target, hint in violations:
            tag = "DEBT" if debt_key(rel, kind, target) in DEBT_ALLOWLIST else "NEW"
            print(f"  [{tag}] {kind}: {rel}:{lineno} → {target}  ({hint})")
        if stale:
            print()
            print("  Stale allowlist (no longer detected):")
            for rel, kind, target in stale:
                print(f"    {kind}: {rel} → {target}")
        return 0

    if new:
        print("LAYER DEPS VIOLATION — new cross-layer imports not in DEBT_ALLOWLIST:", file=sys.stderr)
        for rel, lineno, kind, target, hint in new:
            print(f"  {kind}: {rel}:{lineno} → {target}  ({hint})", file=sys.stderr)
        print(
            "\nEither remove the import or, if intentional temporary debt,\n"
            "add (path, kind, target) to DEBT_ALLOWLIST in check_layer_deps.py\n"
            "and document the migration plan.",
            file=sys.stderr,
        )
        return 1

    if stale:
        print(
            "LAYER DEPS WARNING — stale DEBT_ALLOWLIST entries (safe to delete):",
            file=sys.stderr,
        )
        for rel, kind, target in stale:
            print(f"  {kind}: {rel} → {target}", file=sys.stderr)
        # Stale entries do not fail default mode (encourage cleanup via --strict).

    if args.strict and known:
        print(
            f"LAYER DEPS STRICT FAIL — {len(known)} allowlisted debt edge(s) remain:",
            file=sys.stderr,
        )
        for rel, lineno, kind, target, _hint in known:
            print(f"  {kind}: {rel}:{lineno} → {target}", file=sys.stderr)
        return 1

    print(
        f"LAYER DEPS OK — no new crossings "
        f"({len(known)} known debt edge(s) allowlisted)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

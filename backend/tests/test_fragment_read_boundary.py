"""Architectural tests — Fragment read boundary enforcement.

Fragments are Context Adapters. They must not own persistence concerns.
All data access flows through Runtime read ports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_FRAGMENTS_ROOT = Path(__file__).resolve().parent.parent / "app" / "fragments"

_FORBIDDEN_IMPORT_PREFIXES = (
    "app.store.database",
    "app.store.vector",
    "sqlalchemy",
)

_FORBIDDEN_IMPORT_MODULES = frozenset({
    "app.store.database",
    "app.store.vector",
    "app.core.runtime.kernel_instance",
    "app.core.agents.memory_engine",
    "app.core.agents.world_model",
    "app.core.harness.builtin_tools.calendar",
})

_ALLOWED_RUNTIME_IMPORTS = frozenset({
    "app.context_runtime",
    "app.core.runtime",
    "app.core.runtime.read_ports",
    # Pure helpers (no persistence / Kernel bypass).
    "app.core.agents.token_counter",
    "app.core.agents.tool_markup",
})


def _fragment_source_files() -> list[Path]:
    return sorted(_FRAGMENTS_ROOT.rglob("*.py"))


def _collect_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


class TestFragmentReadBoundary:
    """Fragments must not import persistence or bypass read ports."""

    @pytest.mark.parametrize(
        "path",
        _fragment_source_files(),
        ids=lambda p: p.relative_to(_FRAGMENTS_ROOT).as_posix(),
    )
    def test_no_forbidden_imports(self, path: Path):
        violations: list[str] = []
        for lineno, module in _collect_imports(path):
            if module in _FORBIDDEN_IMPORT_MODULES:
                violations.append(f"{path.name}:{lineno} imports forbidden {module!r}")
                continue
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                if module.startswith(prefix):
                    violations.append(f"{path.name}:{lineno} imports forbidden {module!r}")
                    break
        assert not violations, "\n".join(violations)

    @pytest.mark.parametrize(
        "path",
        _fragment_source_files(),
        ids=lambda p: p.relative_to(_FRAGMENTS_ROOT).as_posix(),
    )
    def test_runtime_imports_use_read_ports_only(self, path: Path):
        if path.name == "register.py":
            pytest.skip("registration module is not a fragment adapter")

        violations: list[str] = []
        for lineno, module in _collect_imports(path):
            if not module.startswith("app."):
                continue
            if module in _ALLOWED_RUNTIME_IMPORTS:
                continue
            if module.startswith("app.fragments."):
                continue
            violations.append(f"{path.name}:{lineno} imports {module!r} outside read_ports")
        assert not violations, "\n".join(violations)

    def test_no_db_get_db_in_fragment_sources(self):
        violations: list[str] = []
        for path in _fragment_source_files():
            text = path.read_text(encoding="utf-8")
            if "get_db" in text or "db.get_db" in text:
                violations.append(str(path.relative_to(_FRAGMENTS_ROOT)))
        assert not violations, f"Direct DB access in: {violations}"

    def test_all_data_fragments_import_read_ports(self):
        """Data-producing fragments must route reads through read_ports."""
        data_fragment_modules = [
            "universal/goals.py",
            "universal/conversation_state.py",
            "universal/background.py",
            "mail/__init__.py",
            "calendar/__init__.py",
        ]
        missing: list[str] = []
        for rel in data_fragment_modules:
            path = _FRAGMENTS_ROOT / rel
            text = path.read_text(encoding="utf-8")
            if "read_ports" not in text:
                missing.append(rel)
        assert not missing, f"Missing read_ports import: {missing}"

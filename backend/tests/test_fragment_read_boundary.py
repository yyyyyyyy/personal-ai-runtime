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

    @pytest.mark.parametrize("path", _fragment_source_files(), ids=lambda p: p.relative_to(_FRAGMENTS_ROOT).as_posix())
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

    @pytest.mark.parametrize("path", _fragment_source_files(), ids=lambda p: p.relative_to(_FRAGMENTS_ROOT).as_posix())
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


class TestKernelReadSelectors:
    """New query_state selectors used by read ports."""

    def _make_kernel(self, tmp_path):
        from app.core.runtime.kernel import Kernel
        from app.store.database import Database

        db = Database(db_path=str(tmp_path / "test.db"))
        return Kernel(db=db), db

    def test_query_goals_status_in(self, tmp_path):
        k, _ = self._make_kernel(tmp_path)

        k.emit_event(
            "WorkItemCreated", "work_item", "g1",
            {"work_type": "goal", "title": "Active Goal", "status": "active", "importance": 5, "urgency": 3},
            actor="test",
        )
        k.emit_event(
            "WorkItemCreated", "work_item", "g2",
            {"work_type": "goal", "title": "In Progress Goal", "status": "in_progress", "importance": 4, "urgency": 2},
            actor="test",
        )
        k.emit_event(
            "WorkItemCreated", "work_item", "g3",
            {"title": "Done Goal", "status": "completed", "importance": 10, "urgency": 10},
            actor="test",
        )

        rows = k.query_state(
            "goals",
            status_in=("active", "in_progress"),
            limit=5,
            order="importance_urgency_desc",
        )
        titles = {r["title"] for r in rows}
        assert "Active Goal" in titles
        assert "In Progress Goal" in titles
        assert "Done Goal" not in titles

    def test_query_messages(self, tmp_path):
        _, db = self._make_kernel(tmp_path)
        k, _ = self._make_kernel(tmp_path)

        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, datetime('now'))",
                ("c1", "Test"),
            )
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                ("m1", "c1", "user", "Hello"),
            )

        rows = k.query_state("messages", conversation_id="c1", limit=10)
        assert len(rows) == 1
        assert rows[0]["content"] == "Hello"

    def test_query_inbox_emails(self, tmp_path):
        _, db = self._make_kernel(tmp_path)
        k, _ = self._make_kernel(tmp_path)

        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO inbox_emails
                   (id, sender, subject, preview, received_at, category, importance, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                ("e1", "a@test.com", "Hello", "preview", "2026-06-18", "important", 1, "unread"),
            )
            conn.execute(
                """INSERT INTO inbox_emails
                   (id, sender, subject, preview, received_at, category, importance, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                ("e2", "b@test.com", "Archived", "old", "2026-06-17", "ignorable", 0, "archived"),
            )

        recent = k.query_state("inbox_emails", status_not="archived", limit=10)
        assert len(recent) == 1
        assert recent[0]["subject"] == "Hello"

        search = k.query_state("inbox_emails", search="Archived", limit=10)
        assert len(search) == 1
        assert search[0]["id"] == "e2"

    def test_read_ports_delegate_to_kernel(self, monkeypatch):
        from app.core.runtime import read_ports

        calls: list[tuple] = []

        def fake_query_state(selector: str, **filters):
            calls.append((selector, filters))
            return [{"title": "Test Goal", "status": "active"}]

        monkeypatch.setattr(read_ports.kernel, "query_state", fake_query_state)
        rows = read_ports.query_top_active_goals(limit=3)
        assert rows[0]["title"] == "Test Goal"
        assert calls[0][0] == "goals"
        assert calls[0][1]["status_in"] == ("active", "in_progress")

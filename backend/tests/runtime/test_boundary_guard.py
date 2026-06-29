"""Tests for scripts/check_boundary.py kernel boundary guard."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "check_boundary.py"


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )


class TestBoundaryGuard:
    def test_codebase_passes_with_allowlisted_debt(self):
        """Known debt is allowlisted; CI passes but reports debt count."""
        result = run_check()
        assert result.returncode == 0, result.stderr or result.stdout
        assert "KERNEL BOUNDARY OK" in result.stdout

    def test_inventory_lists_known_violations(self):
        result = run_check("--inventory")
        assert result.returncode == 0, result.stderr or result.stdout
        assert "Total violations: 0" in result.stdout
        assert "New (would fail CI): 0" in result.stdout

    def test_strict_mode_passes_when_allowlist_empty(self):
        result = run_check("--strict")
        assert result.returncode == 0, result.stderr or result.stdout
        assert "KERNEL BOUNDARY OK" in result.stdout

    def test_new_violation_not_in_allowlist_fails(self, tmp_path):
        fake_app = tmp_path / "app" / "product"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "evil_brief.py"
        bad_file.write_text(
            'rows = conn.execute("SELECT * FROM goals WHERE status = \'active\'").fetchall()',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import (
                KNOWN_VIOLATION_ALLOWLIST,
                partition_violations,
                scan_app_root,
            )

            violations = scan_app_root(tmp_path / "app")
            _known, new = partition_violations(violations, KNOWN_VIOLATION_ALLOWLIST)
            assert len(new) == 1
            assert new[0][3] == "goals"
        finally:
            sys.path.pop(0)

    def test_violation_detected_mcp_hub_import(self, tmp_path):
        fake_app = tmp_path / "app" / "product"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "evil.py"
        bad_file.write_text("from app.core.harness.mcp_hub import mcp_hub\n", encoding="utf-8")

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert len(violations) == 1
            assert violations[0][3] == "mcp_hub"
            assert violations[0][4] == "import"
        finally:
            sys.path.pop(0)

    def test_violation_detected_dml_write(self, tmp_path):
        fake_app = tmp_path / "app" / "api" / "evil"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "bad.py"
        bad_file.write_text('conn.execute("INSERT INTO goals (id) VALUES (?)", ("x",))', encoding="utf-8")

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert len(violations) == 1
            assert violations[0][3] == "goals"
            assert violations[0][4] == "dml_write"
        finally:
            sys.path.pop(0)

    def test_violation_detected_select_in_product(self, tmp_path):
        fake_app = tmp_path / "app" / "product"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "leak.py"
        bad_file.write_text(
            'rows = conn.execute("SELECT * FROM tasks WHERE status = \'pending\'").fetchall()',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert len(violations) == 1
            assert violations[0][3] == "tasks"
            assert violations[0][4] == "select"
        finally:
            sys.path.pop(0)

    def test_kernel_space_excluded(self, tmp_path):
        fake_app = tmp_path / "app" / "core" / "runtime" / "kernel"
        fake_app.mkdir(parents=True)
        ok_file = fake_app / "kernel.py"
        ok_file.write_text(
            'row = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert violations == []
        finally:
            sys.path.pop(0)

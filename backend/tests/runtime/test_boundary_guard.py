"""Tests for scripts/check_boundary.py kernel boundary guard."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "check_boundary.py"


def run_check() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )


class TestBoundaryGuard:
    def test_clean_codebase_passes(self):
        result = run_check()
        assert result.returncode == 0, result.stderr or result.stdout
        assert "KERNEL BOUNDARY OK" in result.stdout

    def test_violation_detected_mcp_hub_import(self, tmp_path):
        """mcp_hub import in User Space must fail."""
        fake_app = tmp_path / "app" / "api"
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
        """A deliberate DML write outside kernel/ must fail the guard."""
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

    def test_violation_detected_select_in_runtime_engine(self, tmp_path):
        """Governed SELECT in User Space must fail."""
        fake_app = tmp_path / "app" / "core" / "runtime"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "task_engine.py"
        bad_file.write_text(
            'row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()',
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

    def test_violation_detected_select_in_agents(self, tmp_path):
        """Governed SELECT in agents/ must fail."""
        fake_app = tmp_path / "app" / "core" / "agents"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "evil.py"
        bad_file.write_text(
            'rows = conn.execute("SELECT * FROM goals WHERE status = \'active\'").fetchall()',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert len(violations) == 1
            assert violations[0][3] == "goals"
        finally:
            sys.path.pop(0)

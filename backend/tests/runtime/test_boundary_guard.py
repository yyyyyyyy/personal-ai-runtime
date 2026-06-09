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

    def test_violation_detected(self, tmp_path):
        """A deliberate violation outside kernel/ must fail the guard."""
        fake_app = tmp_path / "app" / "evil"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "bad.py"
        bad_file.write_text('conn.execute("INSERT INTO goals (id) VALUES (?)", ("x",))', encoding="utf-8")

        # Run the scanner logic inline against the fake tree
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_boundary import scan_app_root

            violations = scan_app_root(tmp_path / "app")
            assert len(violations) == 1
            assert violations[0][3] == "goals"
        finally:
            sys.path.pop(0)

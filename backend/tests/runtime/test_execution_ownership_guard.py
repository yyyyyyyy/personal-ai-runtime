"""Tests for scripts/check_execution_ownership.py execution ownership guard."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "check_execution_ownership.py"


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )


class TestExecutionOwnershipGuard:
    def test_codebase_passes(self):
        result = run_check()
        assert result.returncode == 0, result.stderr or result.stdout
        assert "EXECUTION OWNERSHIP OK" in result.stdout

    def test_inventory_zero_bypasses(self):
        result = run_check("--inventory")
        assert result.returncode == 0, result.stderr or result.stdout
        assert "Total bypasses: 0" in result.stdout
        assert "New (would fail CI): 0" in result.stdout

    def test_strict_mode_passes_when_allowlist_empty(self):
        result = run_check("--strict")
        assert result.returncode == 0, result.stderr or result.stdout
        assert "EXECUTION OWNERSHIP OK" in result.stdout

    def test_allowlist_is_empty(self):
        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_execution_ownership import BYPASS_ALLOWLIST

            assert len(BYPASS_ALLOWLIST) == 0
        finally:
            sys.path.pop(0)

    def test_missing_execution_id_detected(self, tmp_path):
        fake_app = tmp_path / "app" / "product"
        fake_app.mkdir(parents=True)
        bad_file = fake_app / "evil.py"
        bad_file.write_text(
            'await kernel.invoke_capability("read_file", {"path": "/tmp/x"}, actor="user")',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_execution_ownership import scan_app_root

            _known, new_violations = scan_app_root(tmp_path / "app", frozenset())
            assert len(new_violations) == 1
            assert new_violations[0][3] == "missing execution_id"
        finally:
            sys.path.pop(0)

    def test_kernel_space_excluded(self, tmp_path):
        fake_app = tmp_path / "app" / "core" / "runtime" / "kernel"
        fake_app.mkdir(parents=True)
        ok_file = fake_app / "kernel.py"
        ok_file.write_text(
            'await self.invoke_capability("read_file", {"path": "/tmp/x"}, actor="user")',
            encoding="utf-8",
        )

        sys.path.insert(0, str(BACKEND))
        try:
            from scripts.check_execution_ownership import scan_app_root

            known, new_violations = scan_app_root(tmp_path / "app", frozenset())
            assert known == []
            assert new_violations == []
        finally:
            sys.path.pop(0)

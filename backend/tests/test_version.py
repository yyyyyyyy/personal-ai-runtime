"""Tests for version module."""

import json
import subprocess
import sys
from pathlib import Path

from app.version import APP_NAME, VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_app_name():
    assert APP_NAME == "Personal AI Runtime"


def test_version_is_set():
    assert VERSION is not None
    assert len(VERSION) > 0
    assert VERSION.count(".") >= 1  # semver: major.minor.patch


def test_version_file_matches_module():
    version_file = REPO_ROOT / "VERSION"
    assert version_file.is_file()
    assert version_file.read_text(encoding="utf-8").strip() == VERSION


def test_package_json_versions_match():
    for rel in ("frontend/package.json", "desktop/package.json"):
        data = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        assert data["version"] == VERSION, rel


def test_check_version_sync_script_passes():
    script = REPO_ROOT / "backend" / "scripts" / "check_version_sync.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

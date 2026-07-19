"""Tests for Git MCP server path sandbox."""

import json
import subprocess
from pathlib import Path

import pytest

from app.core.harness.builtin_tools.filesystem import FilesystemServer
from app.core.harness.builtin_tools.git import GitServer


def _error(result: str) -> str:
    return json.loads(result).get("error", "")


@pytest.fixture
def nested_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def test_git_status_outside_allowed_dirs_rejected(tmp_path, nested_repo, monkeypatch):
    """repo_path must respect filesystem allowed dirs (default: project root)."""
    fs = FilesystemServer(allowed_dirs=[str(tmp_path / "other")])
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.git.filesystem_server",
        fs,
    )
    server = GitServer()
    err = _error(server.status(str(nested_repo)))
    assert "Access denied" in err


def test_git_status_inside_allowed_dirs_ok(tmp_path, nested_repo, monkeypatch):
    fs = FilesystemServer(allowed_dirs=[str(tmp_path)])
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.git.filesystem_server",
        fs,
    )
    server = GitServer()
    result = json.loads(server.status(str(nested_repo)))
    assert "error" not in result, result
    assert result["exit_code"] == 0

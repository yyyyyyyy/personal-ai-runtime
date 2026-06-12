"""Tests for filesystem path boundary checks."""

import json
import sys
from pathlib import Path

import pytest

from app.core.harness.mcp_servers.filesystem import FilesystemServer


@pytest.fixture
def fs_server(tmp_path: Path) -> FilesystemServer:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    return FilesystemServer(allowed_dirs=[str(allowed)])


def test_read_inside_allowed(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    target = allowed / "ok.txt"
    target.write_text("hello", encoding="utf-8")
    result = fs_server.read_file(str(target))
    assert result == "hello"


def test_prefix_bypass_rejected(fs_server: FilesystemServer, tmp_path: Path):
    sibling = tmp_path / "allowed_attacker"
    sibling.mkdir()
    secret = sibling / "secret.txt"
    secret.write_text("nope", encoding="utf-8")

    result = json.loads(fs_server.read_file(str(secret)))
    assert "error" in result
    assert "denied" in result["error"].lower()


def test_write_outside_allowed_rejected(fs_server: FilesystemServer, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    result = json.loads(fs_server.write_file(str(outside), "secret"))
    assert "error" in result
    assert "denied" in result["error"].lower()


def test_list_directory_outside_allowed_rejected(
    fs_server: FilesystemServer, tmp_path: Path,
):
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    result = json.loads(fs_server.list_directory(str(outside)))
    assert "error" in result
    assert "denied" in result["error"].lower()


def test_search_files_outside_allowed_rejected(
    fs_server: FilesystemServer, tmp_path: Path,
):
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    result = json.loads(fs_server.search_files(str(outside), "foo"))
    assert "error" in result
    assert "denied" in result["error"].lower()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows path case")
def test_windows_prefix_bypass():
    # Simulate Windows-style adjacent user dirs without relying on C:\Users layout
    base = Path("C:/Users/testuser")
    attacker = Path("C:/Users/testuser_attacker/secret.txt")
    server = FilesystemServer(allowed_dirs=[str(base)])
    assert server._is_safe(str(attacker)) is False

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


def test_write_protected_path_rejected(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    kernel_dir = allowed / "kernel"
    kernel_dir.mkdir(parents=True)
    target = kernel_dir / "kernel.py"
    target.write_text("original", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(kernel_dir)],
    )
    result = json.loads(server.write_file(str(target), "hacked"))
    assert "error" in result
    assert "protected" in result["error"].lower()
    assert target.read_text(encoding="utf-8") == "original"


def test_apply_patch_success(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    target = allowed / "app.py"
    target.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    result = json.loads(
        fs_server.apply_patch(str(target), "return 'hi'", "return 'hello'")
    )
    assert result["success"] is True
    assert result["replacements"] == 1
    assert "return 'hello'" in target.read_text(encoding="utf-8")


def test_apply_patch_old_string_not_found(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    target = allowed / "app.py"
    target.write_text("unchanged", encoding="utf-8")

    result = json.loads(
        fs_server.apply_patch(str(target), "missing", "new")
    )
    assert "error" in result
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_apply_patch_ambiguous_without_replace_all(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    target = allowed / "app.py"
    target.write_text("foo\nfoo\n", encoding="utf-8")

    result = json.loads(
        fs_server.apply_patch(str(target), "foo", "bar")
    )
    assert "error" in result
    assert result.get("occurrences") == 2


def test_apply_patch_protected_path_rejected(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    policy = allowed / "policy.json"
    policy.write_text("{}", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(policy)],
    )
    result = json.loads(server.apply_patch(str(policy), "{}", '{"a":1}'))
    assert "error" in result
    assert "protected" in result["error"].lower()


def test_apply_patch_empty_old_string_rejected(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    target = allowed / "app.py"
    target.write_text("unchanged", encoding="utf-8")

    result = json.loads(fs_server.apply_patch(str(target), "", "new"))
    assert "error" in result
    assert "empty" in result["error"].lower()
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_write_env_variants_protected(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    env = allowed / ".env"
    env_local = allowed / ".env.local"
    env.write_text("KEY=1", encoding="utf-8")
    env_local.write_text("KEY=2", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(env)],
    )
    for target in (env, env_local):
        result = json.loads(server.write_file(str(target), "hacked"))
        assert "error" in result
        assert "protected" in result["error"].lower()


def test_write_env_subdirectory_protected(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    subdir = allowed / "backend"
    subdir.mkdir()
    env_local = subdir / ".env.local"
    env_local.write_text("KEY=2", encoding="utf-8")

    server = FilesystemServer(allowed_dirs=[str(allowed)])
    result = json.loads(server.write_file(str(env_local), "hacked"))
    assert "error" in result
    assert "protected" in result["error"].lower()
    assert env_local.read_text(encoding="utf-8") == "KEY=2"


def test_write_env_example_allowed(fs_server: FilesystemServer, tmp_path: Path):
    allowed = tmp_path / "allowed"
    env = allowed / ".env"
    env_example = allowed / ".env.example"
    env.write_text("SECRET=1", encoding="utf-8")
    env_example.write_text("# template", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(env)],
    )
    blocked = json.loads(server.write_file(str(env), "hacked"))
    assert "protected" in blocked["error"].lower()

    result = json.loads(server.write_file(str(env_example), "NOTION_TOKEN=\n"))
    assert result["success"] is True
    assert "NOTION_TOKEN" in env_example.read_text(encoding="utf-8")


def test_default_protected_paths_appends_extra(monkeypatch, tmp_path):
    extra = tmp_path / "extra_secret"
    extra.mkdir()
    monkeypatch.setattr(
        "app.core.harness.mcp_servers.filesystem.settings.filesystem_protected_paths",
        str(extra),
    )
    from app.core.harness.mcp_servers.filesystem import default_protected_paths

    paths = default_protected_paths()
    assert any("kernel" in p for p in paths)
    assert str(extra.resolve()) in [str(Path(p).resolve()) for p in paths]

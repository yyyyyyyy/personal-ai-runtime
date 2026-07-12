"""Tests for filesystem path boundary checks."""

import json
import sys
from pathlib import Path

import pytest

from app.core.harness.builtin_tools.filesystem import FilesystemServer


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
        "app.core.harness.builtin_tools.filesystem.settings.filesystem_protected_paths",
        str(extra),
    )
    from app.core.harness.builtin_tools.filesystem import default_protected_paths

    paths = default_protected_paths()
    assert any("kernel" in p for p in paths)
    assert str(extra.resolve()) in [str(Path(p).resolve()) for p in paths]


def test_write_through_symlink_rejected(fs_server: FilesystemServer, tmp_path: Path):
    """A symlink planted inside an allowed dir must not let writes escape.

    Without the symlink defense, resolve() would follow the link into a
    protected location (e.g. /etc), defeating _is_protected.
    """
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside_target"
    outside.write_text("real", encoding="utf-8")

    link = allowed / "escape"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    result = json.loads(fs_server.write_file(str(link), "hacked"))
    assert "error" in result
    assert "symlink" in result["error"].lower()
    # Underlying target must be untouched.
    assert outside.read_text(encoding="utf-8") == "real"


def test_write_to_normal_file_under_allowed_still_works(
    fs_server: FilesystemServer, tmp_path: Path,
):
    """Regression guard: regular writes inside the allowed dir are unaffected."""
    allowed = tmp_path / "allowed"
    target = allowed / "normal.txt"
    result = json.loads(fs_server.write_file(str(target), "ok"))
    assert result["success"] is True


def test_read_protected_path_rejected(fs_server: FilesystemServer, tmp_path: Path):
    """read_file must refuse protected paths, not just out-of-bounds paths.

    Previously read_file only checked _is_safe, so a protected file inside an
    allowed dir (e.g. ~/.ssh/id_rsa when home was allowed) was readable.
    """
    allowed = tmp_path / "allowed"
    secret_dir = allowed / "secrets"
    secret_dir.mkdir()
    secret = secret_dir / "id_rsa"
    secret.write_text("PRIVATE", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(secret_dir)],
    )
    result = json.loads(server.read_file(str(secret)))
    assert "error" in result
    assert "protected" in result["error"].lower()


def test_read_env_file_rejected(fs_server: FilesystemServer, tmp_path: Path):
    """.env files are protected on read as well as write (any directory)."""
    allowed = tmp_path / "allowed"
    env = allowed / ".env"
    env.write_text("SECRET=1", encoding="utf-8")

    # Default protected_paths includes _is_env_secret_file for .env in any dir.
    server = FilesystemServer(allowed_dirs=[str(allowed)])
    result = json.loads(server.read_file(str(env)))
    assert "error" in result
    assert "protected" in result["error"].lower()


def test_list_directory_skips_protected_entries(
    fs_server: FilesystemServer, tmp_path: Path,
):
    """list_directory must not enumerate contents of a protected subdir."""
    allowed = tmp_path / "allowed"
    ssh_dir = allowed / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_rsa").write_text("PRIVATE", encoding="utf-8")
    normal = allowed / "ok.txt"
    normal.write_text("hi", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(ssh_dir)],
    )
    result = json.loads(server.list_directory(str(allowed)))
    names = [item["name"] for item in result["items"]]
    assert "ok.txt" in names
    assert ".ssh" not in names, "protected subdir must be hidden from listing"


def test_search_files_skips_protected_entries(
    fs_server: FilesystemServer, tmp_path: Path,
):
    """search_files must not return protected files."""
    allowed = tmp_path / "allowed"
    ssh_dir = allowed / ".ssh"
    ssh_dir.mkdir()
    key = ssh_dir / "id_rsa"
    key.write_text("PRIVATE", encoding="utf-8")
    normal = allowed / "id_rsa_template.txt"
    normal.write_text("template", encoding="utf-8")

    server = FilesystemServer(
        allowed_dirs=[str(allowed)],
        protected_paths=[str(ssh_dir)],
    )
    result = json.loads(server.search_files(str(allowed), "id_rsa"))
    paths = [r["name"] for r in result["results"]]
    assert "id_rsa_template.txt" in paths
    assert "id_rsa" not in paths, "protected file must be hidden from search"


def test_default_allowed_dirs_excludes_home(monkeypatch):
    """The default allowed_dirs no longer includes Path.home().

    Previously home was included by default, exposing dotfiles/secrets. Now
    only the project root is allowed unless FILESYSTEM_ALLOWED_DIRS is set.
    """
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.filesystem.settings.filesystem_allowed_dirs",
        "",
    )
    from pathlib import Path as _Path

    from app.config import BASE_DIR
    from app.core.harness.builtin_tools.filesystem import default_allowed_dirs

    dirs = default_allowed_dirs()
    assert str(_Path(BASE_DIR).resolve()) in [_Path(d).resolve().as_posix() for d in dirs] or \
           str(_Path(BASE_DIR).resolve()) in dirs
    home = str(_Path.home().resolve())
    assert home not in [_Path(d).resolve().as_posix() for d in dirs], \
        "home directory must NOT be in the default allowed list"

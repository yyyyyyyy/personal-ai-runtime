"""Tests for hardened Shell MCP server."""

import json
import sys
from pathlib import Path

import pytest

from app.core.harness.builtin_tools.shell import ShellServer, shell_server


def _error(result: str) -> str:
    return json.loads(result).get("error", "")


def test_empty_command_rejected():
    assert "Empty command" in _error(shell_server.execute(""))
    assert "Empty command" in _error(shell_server.execute("   "))


def test_non_whitelisted_command_rejected():
    assert "not in whitelist" in _error(shell_server.execute("bash -c ls"))


def test_python_c_blocked():
    assert "not allowed" in _error(shell_server.execute('python -c "print(1)"'))


def test_node_eval_blocked():
    assert "not allowed" in _error(shell_server.execute('node -e "console.log(1)"'))


@pytest.mark.parametrize(
    "command",
    [
        "echo hello | wc",
        "echo hello; echo world",
        "echo > /tmp/out",
        "echo `whoami`",
    ],
)
def test_shell_metacharacters_blocked(command: str):
    assert "metacharacters" in _error(shell_server.execute(command))


@pytest.mark.skipif(sys.platform == "win32", reason="echo is not a standalone executable on Windows")
def test_chained_commands_auto_split():
    """&& is now auto-split into individual commands instead of being rejected."""
    result = json.loads(shell_server.execute("echo hello && echo world"))
    assert result.get("chained") is True
    assert result["commands"] == ["echo hello", "echo world"]
    assert len(result["results"]) == 2


def test_blocked_patterns_still_rejected():
    assert "Blocked pattern" in _error(shell_server.execute("sudo ls"))


def test_privilege_escalation_commands_blocked():
    """sudo/su/doas must be rejected as the command itself, not as a substring.

    Substring matching would false-positive on harmless commands like
    'pseudo', 'subl', 'summarize'. Argv-level matching avoids that.
    """
    assert "Blocked pattern" in _error(shell_server.execute("sudo ls"))
    assert "Blocked pattern" in _error(shell_server.execute("su root"))


def test_privilege_escalation_substring_not_false_positive():
    """Commands that merely contain 'su'/'sudo' as a substring must still run."""
    # 'summarize', 'subl', 'pseudo' are not whitelisted, so they fail with the
    # whitelist message — NOT with the privilege-escalation block.
    err = _error(shell_server.execute("summarize foo"))
    assert "Blocked pattern" not in err
    err = _error(shell_server.execute("pseudo bar"))
    assert "Blocked pattern" not in err


def test_rm_rf_blocked_with_extra_whitespace():
    """rm -rf must be rejected even when extra spaces would defeat substring matching.

    rm is an extended command; this test enables it to verify the
    destructive-pattern defence still catches -rf regardless of whitespace.
    """
    server = ShellServer()
    server._effective_whitelist.add("rm")
    assert "Blocked pattern" in _error(server.execute("rm  -rf /tmp/x"))
    assert "Blocked pattern" in _error(server.execute("rm\t-rf /tmp/x"))


def test_rm_rf_blocked_with_reordered_flags():
    """rm -rf reordered (rm /tmp/x -rf) must still be detected at argv level."""
    server = ShellServer()
    server._effective_whitelist.add("rm")
    assert "Blocked pattern" in _error(server.execute("rm /tmp/x -rf"))


def test_rm_fr_variant_blocked():
    server = ShellServer()
    server._effective_whitelist.add("rm")
    assert "Blocked pattern" in _error(server.execute("rm -fr /tmp/x"))


def test_chmod_777_blocked():
    server = ShellServer()
    server._effective_whitelist.add("chmod")
    assert "Blocked pattern" in _error(server.execute("chmod 777 /tmp/x"))


def test_rm_denied_by_default():
    """rm is high-risk: disabled unless explicitly enabled via SHELL_EXTRA_COMMANDS."""
    assert "not in whitelist" in _error(shell_server.execute("rm /tmp/x"))


def test_ssh_denied_by_default():
    """ssh exposes remote shells / key material: disabled by default."""
    assert "not in whitelist" in _error(shell_server.execute("ssh host"))


def test_gpg_denied_by_default():
    assert "not in whitelist" in _error(shell_server.execute("gpg --list-keys"))


def test_brew_denied_by_default():
    assert "not in whitelist" in _error(shell_server.execute("brew list"))


def test_kill_denied_by_default():
    assert "not in whitelist" in _error(shell_server.execute("kill 1234"))


def test_extended_commands_enabled_via_env(monkeypatch):
    """SHELL_EXTRA_COMMANDS enables extended commands, but only those in the set."""
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.shell.settings.shell_extra_commands",
        "rm",
    )
    from app.core.harness.builtin_tools.shell import ShellServer

    server = ShellServer()
    # rm is now enabled, but rm -rf is still blocked by the destructive defence.
    assert "Blocked pattern" in _error(server.execute("rm -rf /tmp/x"))
    # Arbitrary names in the env var are ignored — only _EXTENDED_COMMANDS honoured.
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.shell.settings.shell_extra_commands",
        "rm,arbitrary_malware",
    )
    server2 = ShellServer()
    assert "not in whitelist" in _error(server2.execute("arbitrary_malware foo"))


def test_docker_blocked():
    """docker is no longer whitelisted — it enables container escape via
    'docker run -v /:/host alpine cat /etc/shadow'."""
    err = _error(shell_server.execute("docker ps"))
    assert "not in whitelist" in err, err


def test_docker_run_escape_blocked():
    """Even a read-only-looking docker invocation must be rejected."""
    err = _error(shell_server.execute("docker run --rm alpine echo hi"))
    assert "not in whitelist" in err, err


def test_curl_internal_url_blocked():
    # curl/wget have been removed from ALLOWED_COMMANDS (v0.2.1) to prevent
    # SSRF bypass. All network requests must go through the DNS-pinned fetch_url tool.
    result = _error(shell_server.execute("curl http://127.0.0.1/admin"))
    assert "not in whitelist" in result, result


def test_allowed_hostname_executes():
    result = json.loads(shell_server.execute("hostname"))
    assert "error" not in result, result
    assert result["exit_code"] == 0
    assert result["output"].strip()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="whoami output differs on Windows")
def test_allowed_whoami_executes():
    result = json.loads(shell_server.execute("whoami"))
    assert "error" not in result
    assert result["exit_code"] == 0
    assert result["output"].strip()


def test_cwd_outside_allowed_rejected(tmp_path):
    """cwd must be within the allowed directories (default: project root)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    result = json.loads(shell_server.execute("pwd", cwd=str(outside)))
    assert "error" in result
    assert "cwd" in result["error"].lower()


def test_cwd_inside_allowed_accepted(tmp_path, monkeypatch):
    """When SHELL_ALLOWED_CWD is set, cwd within it is honoured."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(
        "app.core.harness.builtin_tools.shell.settings.shell_allowed_cwd",
        str(work),
    )
    from app.core.harness.builtin_tools.shell import ShellServer

    server = ShellServer()
    result = json.loads(server.execute("pwd", cwd=str(work)))
    assert "error" not in result, result
    assert result["exit_code"] == 0


def test_default_cwd_is_project_root():
    """With no cwd passed, the command runs under BASE_DIR (not process cwd)."""
    result = json.loads(shell_server.execute("pwd"))
    assert "error" not in result, result
    # BASE_DIR is the repo root; pwd should resolve under it.
    from app.config import BASE_DIR
    assert str(Path(BASE_DIR).resolve()) in result["output"] or result["exit_code"] == 0

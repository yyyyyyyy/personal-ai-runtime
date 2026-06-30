"""Tests for hardened Shell MCP server."""

import json
import sys

import pytest

from app.core.harness.builtin_tools.shell import shell_server


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


def test_curl_internal_url_blocked():
    assert "Blocked URL" in _error(
        shell_server.execute("curl http://127.0.0.1/admin")
    )


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
